import os
import io
import json
import boto3
import tempfile
import logging
import numpy as np
import base64
import time
from langchain_aws import BedrockEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.docstore.document import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
import faiss
from PIL import Image

# Logging setup
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Clients
s3 = boto3.client("s3")
textract = boto3.client("textract")
bedrock_runtime = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))

BUCKET = os.environ.get("S3_BUCKET")
if not BUCKET:
    raise ValueError("S3_BUCKET environment variable must be set")

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
            s3_event = json.loads(body)
            s3_record = s3_event["Records"][0]
            s3_bucket = s3_record["s3"]["bucket"]["name"]
            s3_key = s3_record["s3"]["object"]["key"]

        logger.info(f"Processing file: s3://{s3_bucket}/{s3_key}")
        base_name = os.path.splitext(os.path.basename(s3_key))[0]
        
        # Check cancellation marker
        check_cancelled(base_name)

        with tempfile.TemporaryDirectory() as tmpdir:
            # Sanitize filename to prevent path traversal
            safe_filename = os.path.basename(s3_key).replace('..', '').replace('/', '').replace('\\', '')
            if not safe_filename or safe_filename.startswith('.'):
                safe_filename = 'document.pdf'
            local_path = os.path.join(tmpdir, safe_filename)
            s3.download_file(s3_bucket, s3_key, local_path)
            logger.info(f"Downloaded {os.path.getsize(local_path)} bytes to {local_path}")

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
                                        
                                        # Check and upscale small images
                                        try:
                                            img = Image.open(io.BytesIO(img_data))
                                            width, height = img.size
                                            
                                            # Skip tiny images (likely icons)
                                            if width < 50 or height < 50:
                                                logger.info(f"Skipping tiny image: {width}x{height}")
                                                continue
                                            
                                            # Upscale small images for better analysis
                                            if width < 300 or height < 300:
                                                scale = max(300 / width, 300 / height)
                                                new_size = (int(width * scale), int(height * scale))
                                                img = img.resize(new_size, Image.Resampling.LANCZOS)
                                                logger.info(f"Upscaled {width}x{height} to {img.size}")
                                                
                                                buffer = io.BytesIO()
                                                img.save(buffer, format='JPEG', quality=95)
                                                img_data = buffer.getvalue()
                                        except Exception as size_e:
                                            logger.warning(f"Image size check failed: {size_e}")
                                        
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
                                                raise Exception("Claude analysis returned generic message")
                                        except Exception as e:
                                            logger.error(f"Claude analysis failed: {e}")
                                            # Fallback: generic description
                                            description = f"Image from page {page_num} of {os.path.basename(s3_key).replace('.pdf', '')}"
                                        
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
                            logger.info(f"Page {i} has minimal text, using OCR")
                            # Use OCR for this page
                            try:
                                from pdf2image import convert_from_path
                                import io as iolib
                                
                                # Check cancellation before OCR
                                check_cancelled(base_name)
                                
                                # Convert just this page to image
                                images = convert_from_path(local_path, first_page=i, last_page=i, dpi=200)
                                if images:
                                    import pytesseract
                                    
                                    # Check cancellation before OCR
                                    check_cancelled(base_name)
                                    
                                    # Quick test with fast OCR to check quality
                                    test_data = pytesseract.image_to_data(images[0], lang='heb+eng+tur', output_type=pytesseract.Output.DICT, timeout=30)
                                    confidences = [int(c) for c in test_data['conf'] if c != '-1' and str(c).isdigit()]
                                    avg_confidence = sum(confidences) / len(confidences) if confidences else 100
                                    
                                    # If high confidence (>70), use fast OCR. If low, use preprocessing
                                    if avg_confidence > 70:
                                        # Fast path for printed text
                                        ocr_text = pytesseract.image_to_string(images[0], lang='heb+eng+tur', timeout=60)
                                        logger.info(f"Page {i} Fast OCR (conf={avg_confidence:.1f}): {len(ocr_text)} chars")
                                    else:
                                        # Slow path with preprocessing for handwritten/low quality
                                        logger.info(f"Page {i} Low confidence ({avg_confidence:.1f}), using enhanced OCR")
                                        from PIL import ImageEnhance, ImageFilter, Image
                                        import cv2
                                        
                                        # Check cancellation before enhanced OCR
                                        check_cancelled(base_name)
                                        
                                        # Higher DPI for handwriting
                                        images = convert_from_path(local_path, first_page=i, last_page=i, dpi=300)
                                        img = images[0].convert('L')
                                        
                                        # Enhance contrast
                                        enhancer = ImageEnhance.Contrast(img)
                                        img = enhancer.enhance(2.0)
                                        img = img.filter(ImageFilter.SHARPEN)
                                        
                                        # Denoise and binarize
                                        img_array = np.array(img)
                                        img_array = cv2.fastNlMeansDenoising(img_array, None, 10, 7, 21)
                                        _, img_array = cv2.threshold(img_array, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                                        img = Image.fromarray(img_array)
                                        
                                        ocr_text = pytesseract.image_to_string(img, lang='heb+eng+tur', config='--psm 3 --oem 1', timeout=120)
                                        logger.info(f"Page {i} Enhanced OCR extracted: {len(ocr_text)} chars")
                                    
                                    if ocr_text.strip():
                                        full_text += ocr_text + "\n"
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
            for i, chunk in enumerate(chunks):
                doc = Document(
                    page_content=chunk,
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
                        page_content=f"Image on page {img_meta['page']}: {description}",
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
            
            # ---- Create FAISS index per file ----
            embed = BedrockEmbeddings(model_id="amazon.titan-embed-text-v1", region_name=os.environ.get("AWS_REGION", "us-east-1"))
            logger.info("Building FAISS index...")
            store = FAISS.from_documents(docs, embed)

            # ---- Save index with filename ----
            base_name = os.path.splitext(os.path.basename(s3_key))[0]
            store.save_local(tmpdir)
            
            index_path = os.path.join(tmpdir, "index.faiss")
            pkl_path = os.path.join(tmpdir, "index.pkl")
            
            s3.upload_file(index_path, BUCKET, f"vector_store/{base_name}/index.faiss")
            s3.upload_file(pkl_path, BUCKET, f"vector_store/{base_name}/index.pkl")
            logger.info(f"Uploaded FAISS index to s3://{BUCKET}/vector_store/{base_name}/")

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
        raise e
