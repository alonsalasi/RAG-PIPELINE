import os
import io
import json
import boto3
import tempfile
import logging
import numpy as np
import base64
import time
import requests
import re
from botocore.client import Config
from langchain_aws import BedrockEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.docstore.document import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from semantic_chunker import create_semantic_chunks
import faiss
from PIL import Image
from pdf2image import convert_from_path

# Logging setup with structured format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Thread-safe client initialization
_clients_lock = None
_s3_client = None
_textract_client = None
_bedrock_client = None
_secretsmanager_client = None

def get_s3_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3", config=Config(connect_timeout=5, read_timeout=60))
    return _s3_client

def get_textract_client():
    global _textract_client
    if _textract_client is None:
        _textract_client = boto3.client("textract", config=Config(connect_timeout=5, read_timeout=300))
    return _textract_client

def get_bedrock_client():
    global _bedrock_client
    if _bedrock_client is None:
        region = os.environ.get("AWS_REGION")
        if not region:
            raise ValueError("AWS_REGION environment variable must be set")
        _bedrock_client = boto3.client("bedrock-runtime", region_name=region, config=Config(connect_timeout=5, read_timeout=60))
    return _bedrock_client

def get_secretsmanager_client():
    global _secretsmanager_client
    if _secretsmanager_client is None:
        _secretsmanager_client = boto3.client('secretsmanager')
    return _secretsmanager_client

# Validate required environment variables
BUCKET = os.environ.get("S3_BUCKET")
if not BUCKET:
    logger.error("S3_BUCKET environment variable not configured")
    raise ValueError("S3_BUCKET environment variable must be set")





class ProcessingCancelled(Exception):
    """Exception raised when processing is cancelled by user."""
    pass

def analyze_page_with_claude(image_data):
    """Comprehensive page analysis using Claude Vision - replaces all OCR and image extraction."""
    if not image_data or len(image_data) == 0:
        return None
    
    try:
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1000,
            "messages": [{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_base64
                        }
                    },
                    {
                        "type": "text",
                        "text": "You are an expert document analyst. Analyze this single PDF page image and extract ALL information:\n\n1. **Full Text Transcription:** Transcribe *all* text on the page, including English and Hebrew. Preserve the general layout.\n2. **Table Extraction:** If you see any tables, transcribe them into structured format.\n3. **Image Analysis:** Identify each distinct photo or icon on the page. For *each* one, provide:\n   * A description of the visual\n   * The *exact* caption text from the document that is next to or clearly associated with that visual\n   * BRAND: [brand name if visible]\n   * TYPE: [vehicle type if automotive]\n   * PRIMARY_COLOR: [dominant color]\n   * SECONDARY_COLORS: [other colors]\n\nCombine all of this into a single, comprehensive text report for this page."
                    }
                ]
            }]
        }
        
        bedrock = get_bedrock_client()
        response = bedrock.invoke_model(
            modelId="anthropic.claude-3-haiku-20240307-v1:0",
            body=json.dumps(request_body)
        )
        
        response_body = json.loads(response['body'].read())
        return response_body['content'][0]['text']
        
    except Exception as e:
        logger.warning(f"Page analysis failed: {e}")
        return None



def check_cancelled(base_name):
    """Check if processing was cancelled."""
    if not base_name or not isinstance(base_name, str):
        return False
    
    s3_client = get_s3_client()
    try:
        s3_client.head_object(Bucket=BUCKET, Key=f"cancelled/{base_name}.txt")
        logger.info(f"Processing cancelled: {base_name}")
        s3_client.delete_object(Bucket=BUCKET, Key=f"cancelled/{base_name}.txt")
        raise ProcessingCancelled(f"Processing cancelled for {base_name}")
    except s3_client.exceptions.ClientError as e:
        if e.response['Error']['Code'] == '404':
            return False
        logger.error(f"Error checking cancellation: {type(e).__name__}")
        raise

def process_message(record):
    start_time = time.time()
    try:
        # Check if this is a direct S3 event or SQS message
        if "s3" in record:
            # Direct S3 event
            s3_bucket = record["s3"]["bucket"]["name"]
            s3_key = record["s3"]["object"]["key"]
        else:
            # SQS message with S3 event in body
            body = record.get("body")
            if not body:
                logger.warning("Empty SQS body, skipping")
                return
            try:
                s3_event = json.loads(body)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in SQS body | Error: {type(e).__name__}")
                return
            
            if "Records" not in s3_event or not s3_event["Records"]:
                logger.error("No Records in S3 event")
                return
            
            s3_record = s3_event["Records"][0]
            s3_bucket = s3_record["s3"]["bucket"]["name"]
            s3_key = s3_record["s3"]["object"]["key"]
        
        # Validate S3 key to prevent path traversal and injection attacks
        if not s3_key or '..' in s3_key or s3_key.startswith('/') or '\\' in s3_key:
            logger.error(f"Invalid S3 key detected: path traversal attempt")
            return
        
        # Additional validation for allowed prefixes
        if not s3_key.startswith('uploads/'):
            logger.error(f"S3 key not in allowed uploads prefix")
            return

        logger.info(f"Processing started | Bucket: {s3_bucket} | Key: {s3_key}")
        # Sanitize base_name
        filename = os.path.basename(s3_key)
        base_name = os.path.splitext(filename)[0]
        # Remove any remaining path separators
        base_name = base_name.replace('/', '_').replace('\\', '_')
        logger.info(f"File info | Filename: {filename} | BaseName: {base_name}")
        
        # Check cancellation marker
        check_cancelled(base_name)

        with tempfile.TemporaryDirectory() as tmpdir:
            # Secure filename handling to prevent path traversal
            safe_filename = os.path.basename(s3_key)
            safe_filename = ''.join(c for c in safe_filename if c.isalnum() or c in '._-')
            if not safe_filename or safe_filename.startswith('.') or len(safe_filename) > 255:
                safe_filename = 'document.pdf'
            
            local_path = os.path.join(tmpdir, safe_filename)
            if not os.path.abspath(local_path).startswith(os.path.abspath(tmpdir)):
                logger.error("Path traversal attempt detected")
                raise ValueError("Invalid file path - security violation")
            
            s3_client = get_s3_client()
            try:
                download_start = time.time()
                s3_client.download_file(s3_bucket, s3_key, local_path)
                file_size = os.path.getsize(local_path)
                logger.info(f"Download complete | Size: {file_size} bytes | Time: {time.time() - download_start:.2f}s")
                
                max_size = 100 * 1024 * 1024
                if file_size > max_size:
                    logger.error(f"File too large: {file_size} bytes")
                    raise ValueError(f"File exceeds maximum size of {max_size} bytes")
                    
            except (IOError, OSError) as e:
                logger.error(f"File download failed: {type(e).__name__}")
                raise

            # ---- Simplified Claude Vision Analysis (Test Version) ----
            full_text = ""
            image_metadata = []
            
            if s3_key.lower().endswith('.pdf'):
                try:
                    logger.info(f"Converting PDF to images for Claude analysis")
                    # Only process first 2 pages to avoid timeout
                    all_page_images = convert_from_path(local_path, dpi=150, last_page=2)
                    
                    for page_num, page_image in enumerate(all_page_images, 1):
                        # Check for cancellation every page
                        check_cancelled(base_name)
                        
                        # Convert page image to bytes
                        img_byte_arr = io.BytesIO()
                        page_image.save(img_byte_arr, format='JPEG', quality=85)
                        page_img_data = img_byte_arr.getvalue()
                        
                        # Comprehensive page analysis with Claude
                        logger.info(f"Analyzing page {page_num} with Claude Vision")
                        page_analysis = analyze_page_with_claude(page_img_data)
                        
                        if page_analysis and len(page_analysis.strip()) > 20:
                            full_text += f"\n[PAGE {page_num} ANALYSIS]:\n{page_analysis}\n"
                            logger.info(f"Page {page_num} analysis: {len(page_analysis)} chars")
                            
                            # Always save page as searchable image
                            img_name = f"{base_name}_page{page_num}.jpg"
                            img_key = f"images/{base_name}/{img_name}"
                            
                            s3_client = get_s3_client()
                            s3_client.put_object(
                                Bucket=BUCKET,
                                Key=img_key,
                                Body=page_img_data,
                                ContentType='image/jpeg'
                            )
                            
                            image_metadata.append({
                                'page': page_num,
                                'image_name': img_name,
                                's3_key': img_key,
                                'url': f"https://{BUCKET}.s3.amazonaws.com/{img_key}",
                                'description': page_analysis
                            })
                            logger.info(f"Saved page {page_num} as searchable image: {img_key}")
                        
                        page_image.close()
                    
                    logger.info(f"Claude analysis complete | Pages: {len(all_page_images)} | Images: {len(image_metadata)} | File: {base_name}")
                except Exception as e:
                    logger.error(f"Claude page analysis failed: {e}")
                    # Fallback to basic text extraction
                    try:
                        from pypdf import PdfReader
                        reader = PdfReader(local_path)
                        for page in reader.pages:
                            text = page.extract_text() or ""
                            if text.strip():
                                full_text += text + "\n"
                        logger.info(f"Fallback text extraction: {len(full_text)} chars")
                    except Exception as fallback_e:
                        logger.error(f"Fallback extraction failed: {fallback_e}")
                        full_text = f"Document: {base_name} - Processing failed"
            else:
                logger.warning(f"Unsupported file type: {s3_key}")
                return

            # Clean up the text
            full_text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\xff]', '', full_text)
            full_text = re.sub(r'\s+', ' ', full_text)
            full_text = full_text.strip()
            
            if not full_text.strip() or len(full_text.strip()) < 50:
                logger.warning(f"Insufficient text extracted | Length: {len(full_text)} chars | File: {base_name}")
                # Don't return - still process images even if text extraction failed
                full_text = f"Document: {base_name} - Text extraction failed, content available through images only."

            # Check cancellation before chunking
            check_cancelled(base_name)
            
            # Semantic chunking to preserve table structure
            chunk_start = time.time()
            doc_name = os.path.basename(s3_key).replace('.pdf', '')
            
            try:
                # Use semantic chunking to preserve tables and structure
                docs = create_semantic_chunks(full_text, doc_name, max_chunk_size=1500)
                logger.info(f"Semantic chunking complete | Chunks: {len(docs)} | Time: {time.time() - chunk_start:.2f}s")
                
                # Add image metadata to all chunks
                for doc in docs:
                    doc.metadata.update({
                        "has_images": len(image_metadata) > 0,
                        "image_count": len(image_metadata)
                    })
                    
            except Exception as e:
                logger.warning(f"Semantic chunking failed, falling back to basic chunking: {type(e).__name__}")
                # Fallback to basic chunking if semantic chunking fails
                splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
                chunks = splitter.split_text(full_text)
                docs = []
                for i, chunk in enumerate(chunks):
                    doc = Document(
                        page_content=f"Document: {doc_name}\n{chunk}",
                        metadata={
                            "source": os.path.basename(s3_key),
                            "chunk_id": i,
                            "total_chunks": len(chunks),
                            "has_images": len(image_metadata) > 0,
                            "image_count": len(image_metadata),
                            "content_type": "text"
                        }
                    )
                    docs.append(doc)
                logger.info(f"Fallback chunking complete | Chunks: {len(docs)} | Time: {time.time() - chunk_start:.2f}s")
            
            # Add image descriptions as searchable documents
            if image_metadata:
                for img_meta in image_metadata:
                    # Use the AI-generated description as the searchable content
                    description = img_meta.get('description', 'Image content')
                    
                    # Extract color information for better search
                    color_keywords = []
                    if 'PRIMARY_COLOR:' in description:
                        primary_color = description.split('PRIMARY_COLOR:')[1].split('\n')[0].strip()
                        if primary_color and primary_color.lower() != 'none':
                            color_keywords.append(primary_color.lower())
                    
                    # Add color keywords to make images more searchable
                    searchable_content = f"Document: {doc_name}\nImage on page {img_meta['page']}: {description}"
                    if color_keywords:
                        searchable_content += f"\nColor tags: {' '.join(color_keywords)}"
                    
                    img_doc = Document(
                        page_content=searchable_content,
                        metadata={
                            "source": os.path.basename(s3_key),
                            "type": "image",
                            "page": img_meta['page'],
                            "image_url": img_meta['url'],
                            "s3_key": img_meta['s3_key'],
                            "description": description
                        }
                    )
                    docs.append(img_doc)
                    logger.info(f"Added image document: {description[:50]}...")
            
            logger.info(f"Document preparation complete | Total docs: {len(docs)} | Images: {len(image_metadata)}")

            # Check cancellation before embedding
            check_cancelled(base_name)
            
            # ---- Master Index Approach ----
            region = os.environ.get("AWS_REGION")
            if not region:
                logger.error("AWS_REGION environment variable not set")
                raise ValueError("AWS_REGION must be configured")
            
            model_id = os.environ.get("EMBEDDINGS_MODEL_ID", "cohere.embed-multilingual-v3")
            
            # Validate documents before embedding - Cohere has 512 token limit
            valid_docs = []
            for doc in docs:
                content = doc.page_content.strip()
                if content and len(content) <= 2000:  # Conservative limit for tokens
                    valid_docs.append(doc)
                elif content:
                    # Truncate to safe length
                    truncated_content = content[:1800] + "..."
                    doc.page_content = truncated_content
                    valid_docs.append(doc)
            
            if not valid_docs:
                logger.error("No valid documents for embedding")
                raise ValueError("No valid documents to embed")
            
            logger.info(f"Embedding {len(valid_docs)} valid documents (filtered from {len(docs)})")
            embed = BedrockEmbeddings(model_id=model_id, region_name=region)
            docs = valid_docs
            
            master_index_dir = os.path.join(tmpdir, "master_index")
            os.makedirs(master_index_dir, exist_ok=True)
            
            master_index_path = os.path.join(master_index_dir, "index.faiss")
            master_pkl_path = os.path.join(master_index_dir, "index.pkl")
            
            # Try to download existing master index
            master_exists = False
            try:
                s3_client.download_file(BUCKET, "vector_store/master/index.faiss", master_index_path)
                s3_client.download_file(BUCKET, "vector_store/master/index.pkl", master_pkl_path)
                logger.info("Downloaded existing master index")
                master_exists = True
            except s3_client.exceptions.ClientError as e:
                if e.response['Error']['Code'] == '404':
                    logger.info("No existing master index, creating new one")
                else:
                    raise
            
            # Load or create master index
            embed_start = time.time()
            if master_exists:
                logger.info("Loading existing master index")
                master_store = FAISS.load_local(master_index_dir, embed, allow_dangerous_deserialization=True)
                existing_count = master_store.index.ntotal
                logger.info(f"Master index loaded | Existing vectors: {existing_count}")
                
                # Add new documents to master index
                master_store.add_documents(docs)
                new_count = master_store.index.ntotal
                logger.info(f"Master index updated | Added: {len(docs)} | Total: {new_count} | Time: {time.time() - embed_start:.2f}s")
            else:
                logger.info(f"Creating new master index | Documents: {len(docs)}")
                master_store = FAISS.from_documents(docs, embed)
                logger.info(f"Master index created | Vectors: {master_store.index.ntotal} | Time: {time.time() - embed_start:.2f}s")
            
            # Save updated master index
            master_store.save_local(master_index_dir)
            
            # Verify files exist
            if not os.path.exists(master_index_path) or not os.path.exists(master_pkl_path):
                logger.error("Master index files not created")
                raise Exception("Failed to create master index files")
            
            # Upload master index
            upload_start = time.time()
            try:
                s3_client.upload_file(master_index_path, BUCKET, "vector_store/master/index.faiss")
                s3_client.upload_file(master_pkl_path, BUCKET, "vector_store/master/index.pkl")
                logger.info(f"Master index uploaded | Bucket: {BUCKET} | Time: {time.time() - upload_start:.2f}s")
            except Exception as e:
                logger.error(f"Master index upload failed | Error: {type(e).__name__} | Details: {str(e)[:100]}")
                raise

            # Mark as processed
            marker_key = f"processed/{base_name}.json"
            marker_content = {
                "source_file": s3_key,
                "status": "processed",
                "images": image_metadata,
                "text_chunks": len(docs) - len(image_metadata),
                "text_preview": full_text[:1000] if full_text else "No text extracted",
                "text_length": len(full_text) if full_text else 0,
                "completed_at": int(time.time())
            }
            
            s3_client = get_s3_client()
            s3_client.put_object(
                Bucket=BUCKET,
                Key=marker_key,
                Body=json.dumps(marker_content),
                ContentType="application/json"
            )
            total_time = time.time() - start_time
            logger.info(f"Processing complete | File: {base_name} | Total time: {total_time:.2f}s | Marker: {marker_key}")

    except ProcessingCancelled as e:
        logger.info(f"Processing cancelled | File: {base_name} | Time: {time.time() - start_time:.2f}s")
        return
    except (ValueError, IOError, OSError) as e:
        logger.error(f"Processing failed | File: {base_name} | Error: {type(e).__name__} | Details: {str(e)[:100]} | Time: {time.time() - start_time:.2f}s")
        raise
    except Exception as e:
        logger.error(f"Unexpected error | File: {base_name} | Error: {type(e).__name__} | Details: {str(e)[:200]} | Time: {time.time() - start_time:.2f}s")
        raise
