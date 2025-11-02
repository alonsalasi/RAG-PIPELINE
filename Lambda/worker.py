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
from botocore.client import Config
from langchain_aws import BedrockEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.docstore.document import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
import faiss
from PIL import Image

# Logging setup
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Clients with timeouts and proper error handling
try:
    s3 = boto3.client("s3", config=Config(connect_timeout=5, read_timeout=60))
    textract = boto3.client("textract", config=Config(connect_timeout=5, read_timeout=300))
    
    region = os.environ.get("AWS_REGION")
    if not region:
        raise ValueError("AWS_REGION environment variable must be set")
    
    bedrock_runtime = boto3.client(
        "bedrock-runtime",
        region_name=region,
        config=Config(connect_timeout=5, read_timeout=60)
    )
except Exception as e:
    logger.error(f"Failed to initialize AWS clients: {e}")
    raise

# Validate required environment variables
BUCKET = os.environ.get("S3_BUCKET")
if not BUCKET:
    logger.error("S3_BUCKET environment variable not configured")
    raise ValueError("S3_BUCKET environment variable must be set")

# Google Vision API key (loaded from Secrets Manager)
GOOGLE_VISION_KEY = None

def get_google_vision_key():
    """Lazy load Google Vision API key from Secrets Manager."""
    global GOOGLE_VISION_KEY
    if GOOGLE_VISION_KEY is None:
        try:
            project_name = os.environ.get('PROJECT_NAME')
            if not project_name:
                logger.info("PROJECT_NAME not set, skipping Google Vision")
                GOOGLE_VISION_KEY = None
                return GOOGLE_VISION_KEY
            
            secret_name = f"{project_name}-google-vision-key"
            secretsmanager = boto3.client('secretsmanager')
            response = secretsmanager.get_secret_value(SecretId=secret_name)
            secret = json.loads(response['SecretString'])
            GOOGLE_VISION_KEY = secret.get('api_key')
            
            if GOOGLE_VISION_KEY and GOOGLE_VISION_KEY not in ['NOT_CONFIGURED', 'PLACEHOLDER_REPLACE_AFTER_APPLY', '']:
                logger.info("Google Vision API key loaded")
            else:
                logger.info("Google Vision API key not configured, using standard OCR")
                GOOGLE_VISION_KEY = None
        except Exception as e:
            logger.warning(f"Could not load Google Vision key: {e}")
            GOOGLE_VISION_KEY = None
    return GOOGLE_VISION_KEY

def detect_handwriting_with_google_vision(image_bytes):
    """Use Google Vision to detect handwriting in an image."""
    api_key = get_google_vision_key()
    if not api_key:
        return None
    
    try:
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        url = f"https://vision.googleapis.com/v1/images:annotate?key={api_key}"
        
        payload = {
            "requests": [{
                "image": {"content": image_base64},
                "features": [{"type": "DOCUMENT_TEXT_DETECTION"}]
            }]
        }
        
        response = requests.post(url, json=payload, timeout=30)
        if response.status_code == 200:
            result = response.json()
            if 'responses' in result and result['responses']:
                text = result['responses'][0].get('fullTextAnnotation', {}).get('text', '')
                if text.strip():
                    logger.info(f"Google Vision extracted {len(text)} chars")
                    return text
        else:
            logger.warning(f"Google Vision API error: {response.status_code}")
    except Exception as e:
        logger.warning(f"Google Vision failed: {e}")
    
    return None

def is_handwritten_page(page_image):
    """Detect if a page contains handwriting by checking OCR confidence."""
    try:
        import pytesseract
        data = pytesseract.image_to_data(page_image, output_type=pytesseract.Output.DICT, timeout=10)
        confidences = [int(c) for c in data['conf'] if c != '-1' and str(c).isdigit()]
        if not confidences:
            return False
        avg_confidence = sum(confidences) / len(confidences)
        # Low confidence (<70) suggests handwriting or poor quality
        return avg_confidence < 70
    except Exception as e:
        logger.warning(f"Handwriting detection failed: {e}")
        return False

class ProcessingCancelled(Exception):
    """Exception raised when processing is cancelled by user."""
    pass

def analyze_image_with_claude(image_data):
    """Analyze image using Claude 3 Sonnet with vision capabilities."""
    try:
        logger.info(f"Starting Claude image analysis, image size: {len(image_data)} bytes")
        
        # Convert image to base64
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        logger.info(f"Image converted to base64, length: {len(image_base64)}")
        
        # Prepare the request for Claude
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 300,
            "messages": [
                {
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
                            "text": "Analyze this image and provide: 1) ALL visible text/words/numbers exactly as written, 2) ALL colors present (be specific: white, silver, black, red, etc), 3) CATEGORY: Is this a 'FULL VEHICLE' (complete car/truck/SUV visible) or 'VEHICLE PART' (wheel, engine, interior, etc) or 'OTHER'?, 4) Brand/logo if clearly visible (spell exactly), 5) Key visual features. Format as: TEXT: [all text seen] COLORS: [all colors] CATEGORY: [FULL VEHICLE or VEHICLE PART or OTHER] TYPE: [specific type like sedan, SUV, wheel, dashboard] BRAND: [brand name or 'none visible'] DETAILS: [other features]. Be thorough and precise."
                        }
                    ]
                }
            ]
        }
        
        logger.info(f"Calling Claude 3 Sonnet...")
        
        # Use Claude models that don't require marketplace subscription
        model_ids = [
            "anthropic.claude-3-haiku-20240307-v1:0"
        ]
        
        response = None
        for model_id in model_ids:
            try:
                logger.info(f"Trying model: {model_id}")
                response = bedrock_runtime.invoke_model(
                    modelId=model_id,
                    body=json.dumps(request_body)
                )
                logger.info(f"Successfully used model: {model_id}")
                break
            except Exception as model_error:
                logger.warning(f"Model {model_id} failed: {model_error}")
                continue
        
        if not response:
            raise Exception("All Claude models failed")
        
        # Parse response
        response_body = json.loads(response['body'].read())
        description = response_body['content'][0]['text']
        
        logger.info(f"Claude analysis successful: {description[:100]}...")
        return description
        
    except Exception as e:
        logger.error(f"Claude analysis failed: {str(e)}")
        logger.error(f"Error type: {type(e).__name__}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise e  # Re-raise to trigger fallback

def check_cancelled(base_name):
    """Check if processing was cancelled."""
    try:
        s3.head_object(Bucket=BUCKET, Key=f"cancelled/{base_name}.txt")
        logger.info(f"Processing cancelled: {base_name}")
        s3.delete_object(Bucket=BUCKET, Key=f"cancelled/{base_name}.txt")
        raise ProcessingCancelled(f"Processing cancelled for {base_name}")
    except s3.exceptions.ClientError as e:
        if e.response['Error']['Code'] == '404':
            return False
        raise

def process_message(record):
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
                logger.warning("Empty SQS body, skipping.")
                return
            try:
                s3_event = json.loads(body)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in SQS body: {e}")
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

        logger.info(f"Processing file: s3://{s3_bucket}/{s3_key}")
        # Sanitize base_name
        filename = os.path.basename(s3_key)
        base_name = os.path.splitext(filename)[0]
        # Remove any remaining path separators
        base_name = base_name.replace('/', '_').replace('\\', '_')
        
        # Check cancellation marker
        check_cancelled(base_name)

        with tempfile.TemporaryDirectory() as tmpdir:
            # Secure filename handling to prevent path traversal
            safe_filename = os.path.basename(s3_key)
            # Remove any dangerous characters
            safe_filename = ''.join(c for c in safe_filename if c.isalnum() or c in '._-')
            if not safe_filename or safe_filename.startswith('.') or len(safe_filename) > 255:
                safe_filename = 'document.pdf'
            
            local_path = os.path.join(tmpdir, safe_filename)
            # Verify the resolved path is within tmpdir (prevent path traversal)
            if not os.path.abspath(local_path).startswith(os.path.abspath(tmpdir)):
                logger.error("Path traversal attempt detected")
                raise ValueError("Invalid file path - security violation")
            
            try:
                s3.download_file(s3_bucket, s3_key, local_path)
                file_size = os.path.getsize(local_path)
                logger.info(f"Downloaded {file_size} bytes")
                
                # Validate file size (prevent DoS)
                max_size = 100 * 1024 * 1024  # 100MB limit
                if file_size > max_size:
                    logger.error(f"File too large: {file_size} bytes (max: {max_size})")
                    return
                    
            except Exception as e:
                logger.error(f"Failed to download file from S3: {e}")
                return

            # ---- Extract images from PDF ----
            image_metadata = []
            if s3_key.lower().endswith('.pdf'):
                try:
                    from pypdf import PdfReader
                    reader = PdfReader(local_path)
                    for page_num, page in enumerate(reader.pages, 1):
                        if '/XObject' in page['/Resources']:
                            xObject = page['/Resources']['/XObject'].get_object()
                            for obj_name in xObject:
                                obj = xObject[obj_name]
                                if obj['/Subtype'] == '/Image':
                                    try:
                                        # Extract image data
                                        if '/Filter' in obj:
                                            if obj['/Filter'] == '/DCTDecode':
                                                img_data = obj._data
                                            elif obj['/Filter'] == '/FlateDecode':
                                                img_data = obj._data
                                            else:
                                                continue
                                        else:
                                            img_data = obj._data
                                        
                                        # Check and upscale small images with proper resource management
                                        img = None
                                        try:
                                            img = Image.open(io.BytesIO(img_data))
                                            width, height = img.size
                                            
                                            if width < 50 or height < 50:
                                                logger.info(f"Skipping tiny image: {width}x{height}")
                                                continue
                                            
                                            if width < 300 or height < 300:
                                                scale = max(300 / width, 300 / height)
                                                new_size = (int(width * scale), int(height * scale))
                                                img = img.resize(new_size, Image.Resampling.LANCZOS)
                                                logger.info(f"Upscaled {width}x{height} to {img.size}")
                                                
                                                with io.BytesIO() as buffer:
                                                    img.save(buffer, format='JPEG', quality=95)
                                                    img_data = buffer.getvalue()
                                        finally:
                                            if img:
                                                img.close()
                                        
                                        # Save image to S3
                                        img_name = f"{base_name}_page{page_num}_img{len(image_metadata)}.jpg"
                                        img_key = f"images/{base_name}/{img_name}"
                                        
                                        s3.put_object(
                                            Bucket=BUCKET,
                                            Key=img_key,
                                            Body=img_data,
                                            ContentType='image/jpeg'
                                        )
                                        
                                        # Analyze image with Claude Vision
                                        try:
                                            description = analyze_image_with_claude(img_data)
                                            if description == "Image content could not be analyzed":
                                                raise ValueError("Claude analysis returned generic message")
                                        except Exception as e:
                                            logger.error(f"Claude analysis failed: {e}")
                                            # Fallback: generic description
                                            base_name_clean = os.path.basename(s3_key).replace('.pdf', '')
                                            description = f"Image from page {page_num} of {base_name_clean}"
                                        
                                        image_metadata.append({
                                            'page': page_num,
                                            'image_name': img_name,
                                            's3_key': img_key,
                                            'url': f"https://{BUCKET}.s3.amazonaws.com/{img_key}",
                                            'description': description
                                        })
                                        logger.info(f"Extracted image from page {page_num}: {img_key}")
                                        logger.info(f"Image description: {description[:100]}...")
                                    except Exception as img_e:
                                        logger.warning(f"Failed to extract image: {img_e}")
                    
                    logger.info(f"Extracted {len(image_metadata)} images from PDF")
                except Exception as e:
                    logger.warning(f"Image extraction failed: {e}")
            
            # ---- OCR-based text extraction ----
            full_text = ""
            
            if s3_key.lower().endswith('.pdf'):
                try:
                    # First try pypdf for text-based PDFs
                    from pypdf import PdfReader
                    reader = PdfReader(local_path)
                    for i, page in enumerate(reader.pages, 1):
                        # Check for cancellation every page
                        check_cancelled(base_name)
                        text = page.extract_text() or ""
                        if text.strip() and len(text.strip()) > 50:  # If we get substantial text
                            logger.info(f"Page {i} extracted via pypdf: {len(text)} chars")
                            full_text += text + "\n"
                        else:
                            logger.info(f"Page {i} has minimal text, checking for handwriting")
                            # Check if handwritten and use Google Vision if available
                            try:
                                from pdf2image import convert_from_path
                                import io as iolib
                                
                                # Check cancellation before OCR
                                check_cancelled(base_name)
                                
                                # Convert just this page to image
                                images = convert_from_path(local_path, first_page=i, last_page=i, dpi=200)
                                if images:
                                    import pytesseract
                                    page_image = images[0]
                                    
                                    # Check cancellation before OCR
                                    check_cancelled(base_name)
                                    
                                    try:
                                        # Check if handwritten
                                        is_handwritten = is_handwritten_page(page_image)
                                        
                                        if is_handwritten:
                                            logger.info(f"Page {i} detected as handwritten, trying Google Vision")
                                            # Try Google Vision for handwriting
                                            img_byte_arr = io.BytesIO()
                                            page_image.save(img_byte_arr, format='PNG')
                                            google_text = detect_handwriting_with_google_vision(img_byte_arr.getvalue())
                                            
                                            if google_text:
                                                full_text += google_text + "\n"
                                                logger.info(f"Page {i} Google Vision extracted: {len(google_text)} chars")
                                            else:
                                                logger.info(f"Page {i} Google Vision unavailable, using enhanced OCR")
                                                # Fallback to enhanced OCR
                                                from PIL import ImageEnhance, ImageFilter
                                                import cv2
                                                
                                                check_cancelled(base_name)
                                                
                                                hq_images = convert_from_path(local_path, first_page=i, last_page=i, dpi=300)
                                                img = hq_images[0].convert('L')
                                                enhancer = ImageEnhance.Contrast(img)
                                                img = enhancer.enhance(2.0)
                                                img = img.filter(ImageFilter.SHARPEN)
                                                img_array = np.array(img)
                                                img_array = cv2.fastNlMeansDenoising(img_array, None, 10, 7, 21)
                                                _, img_array = cv2.threshold(img_array, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                                                processed_img = Image.fromarray(img_array)
                                                ocr_text = pytesseract.image_to_string(processed_img, lang='heb+eng+tur', config='--psm 3 --oem 1', timeout=120)
                                                full_text += ocr_text + "\n"
                                                logger.info(f"Page {i} Enhanced OCR: {len(ocr_text)} chars")
                                                processed_img.close()
                                                img.close()
                                                for hq_img in hq_images:
                                                    hq_img.close()
                                        else:
                                            # Not handwritten, use standard OCR
                                            test_data = pytesseract.image_to_data(page_image, lang='heb+eng+tur', output_type=pytesseract.Output.DICT, timeout=30)
                                            confidences = [int(c) for c in test_data['conf'] if c != '-1' and str(c).isdigit()]
                                            avg_confidence = sum(confidences) / len(confidences) if confidences else 100
                                            
                                            if avg_confidence > 70:
                                                # Fast path for printed text
                                                ocr_text = pytesseract.image_to_string(page_image, lang='heb+eng+tur', timeout=60)
                                                full_text += ocr_text + "\n"
                                                logger.info(f"Page {i} Fast OCR (conf={avg_confidence:.1f}): {len(ocr_text)} chars")
                                            else:
                                                # Low confidence printed text
                                                logger.info(f"Page {i} Low confidence ({avg_confidence:.1f}), using enhanced OCR")
                                                from PIL import ImageEnhance, ImageFilter
                                                import cv2
                                                
                                                check_cancelled(base_name)
                                                
                                                hq_images = convert_from_path(local_path, first_page=i, last_page=i, dpi=300)
                                                img = hq_images[0].convert('L')
                                                enhancer = ImageEnhance.Contrast(img)
                                                img = enhancer.enhance(2.0)
                                                img = img.filter(ImageFilter.SHARPEN)
                                                img_array = np.array(img)
                                                img_array = cv2.fastNlMeansDenoising(img_array, None, 10, 7, 21)
                                                _, img_array = cv2.threshold(img_array, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                                                processed_img = Image.fromarray(img_array)
                                                ocr_text = pytesseract.image_to_string(processed_img, lang='heb+eng+tur', config='--psm 3 --oem 1', timeout=120)
                                                full_text += ocr_text + "\n"
                                                logger.info(f"Page {i} Enhanced OCR: {len(ocr_text)} chars")
                                                processed_img.close()
                                                img.close()
                                                for hq_img in hq_images:
                                                    hq_img.close()
                                    finally:
                                        # Clean up page image
                                        if page_image:
                                            page_image.close()
                                        for img in images:
                                            img.close()
                            except Exception as ocr_e:
                                logger.error(f"OCR failed for page {i}: {ocr_e}")
                                
                except Exception as e:
                    logger.error(f"PDF extraction failed: {e}")
                    return
            else:
                logger.warning(f"Unsupported file type: {s3_key}")
                return

            # Clean up the text - remove excessive whitespace and common OCR artifacts
            full_text = full_text.replace('Scanned by CamScanner', '').strip()
            
            if not full_text.strip() or len(full_text.strip()) < 100:
                logger.warning(f"Insufficient text extracted ({len(full_text)} chars); skipping embedding.")
                return

            # Check cancellation before chunking
            check_cancelled(base_name)
            
            # Split text into chunks
            splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
            chunks = splitter.split_text(full_text)
            
            # Add metadata to chunks including image info
            docs = []
            doc_name = os.path.basename(s3_key).replace('.pdf', '')
            for i, chunk in enumerate(chunks):
                # Prepend document name to chunk for better context
                doc = Document(
                    page_content=f"Document: {doc_name}\n{chunk}",
                    metadata={
                        "source": os.path.basename(s3_key),
                        "chunk_id": i,
                        "total_chunks": len(chunks),
                        "has_images": len(image_metadata) > 0,
                        "image_count": len(image_metadata)
                    }
                )
                docs.append(doc)
            
            # Add image descriptions as searchable documents
            if image_metadata:
                for img_meta in image_metadata:
                    # Use the AI-generated description as the searchable content
                    description = img_meta.get('description', 'Image content')
                    img_doc = Document(
                        page_content=f"Document: {doc_name}\nImage on page {img_meta['page']}: {description}",
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
            
            logger.info(f"Created {len(docs)} chunks")

            # Check cancellation before embedding
            check_cancelled(base_name)
            
            # ---- Master Index Approach ----
            region = os.environ.get("AWS_REGION")
            if not region:
                logger.error("AWS_REGION environment variable not set")
                raise ValueError("AWS_REGION must be configured")
            
            model_id = os.environ.get("EMBEDDINGS_MODEL_ID", "cohere.embed-multilingual-v3")
            embed = BedrockEmbeddings(model_id=model_id, region_name=region)
            
            master_index_dir = os.path.join(tmpdir, "master_index")
            os.makedirs(master_index_dir, exist_ok=True)
            
            master_index_path = os.path.join(master_index_dir, "index.faiss")
            master_pkl_path = os.path.join(master_index_dir, "index.pkl")
            
            # Try to download existing master index
            master_exists = False
            try:
                s3.download_file(BUCKET, "vector_store/master/index.faiss", master_index_path)
                s3.download_file(BUCKET, "vector_store/master/index.pkl", master_pkl_path)
                logger.info("Downloaded existing master index")
                master_exists = True
            except s3.exceptions.ClientError as e:
                if e.response['Error']['Code'] == '404':
                    logger.info("No existing master index, creating new one")
                else:
                    raise
            
            # Load or create master index
            if master_exists:
                logger.info("Loading existing master index...")
                master_store = FAISS.load_local(master_index_dir, embed, allow_dangerous_deserialization=True)
                logger.info(f"Master index loaded with {master_store.index.ntotal} existing vectors")
                
                # Add new documents to master index
                logger.info(f"Adding {len(docs)} new documents to master index...")
                master_store.add_documents(docs)
                logger.info(f"Master index now has {master_store.index.ntotal} total vectors")
            else:
                logger.info(f"Creating new master index with {len(docs)} documents...")
                master_store = FAISS.from_documents(docs, embed)
            
            # Save updated master index
            master_store.save_local(master_index_dir)
            
            # Verify files exist
            if not os.path.exists(master_index_path) or not os.path.exists(master_pkl_path):
                logger.error("Master index files not created")
                raise Exception("Failed to create master index files")
            
            # Upload master index
            try:
                s3.upload_file(master_index_path, BUCKET, "vector_store/master/index.faiss")
                s3.upload_file(master_pkl_path, BUCKET, "vector_store/master/index.pkl")
                logger.info(f"Uploaded master index to s3://{BUCKET}/vector_store/master/")
            except Exception as e:
                logger.error(f"Failed to upload master index: {e}")
                raise

            # ---- Mark as processed ----
            marker_key = f"processed/{base_name}.json"
            marker_content = {
                "source_file": s3_key,
                "status": "processed",
                "images": image_metadata,
                "text_chunks": len(chunks) if 'chunks' in locals() else 0,
                "text_preview": full_text[:500] if 'full_text' in locals() and full_text else "No text extracted",
                "completed_at": int(time.time())
            }
            
            s3.put_object(
                Bucket=BUCKET,
                Key=marker_key,
                Body=json.dumps(marker_content),
                ContentType="application/json"
            )
            logger.info(f"Processing complete marker written to s3://{BUCKET}/{marker_key}")

    except ProcessingCancelled as e:
        logger.info(f"Processing cancelled successfully: {e}")
        return  # Exit cleanly without saving anything
    except Exception as e:
        logger.error(f"Failed processing record: {e}")
        # Don't re-raise to prevent infinite retries
        return
