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
from urllib.parse import unquote_plus
from botocore.client import Config
from langchain_aws import BedrockEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.docstore.document import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from semantic_chunker import create_semantic_chunks
import faiss
from PIL import Image
from pdf2image import convert_from_path
from image_analysis import analyze_image
from office_converter import extract_pptx, extract_docx, extract_xlsx

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

def detect_actual_tables(image):
    """Detect if image contains actual table structures (not just text with | or Hebrew ן)."""
    import cv2
    import numpy as np
    
    img_array = np.array(image)
    gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
    binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2)
    
    # Detect horizontal and vertical lines (actual table borders)
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
    
    horizontal_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel, iterations=2)
    vertical_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vertical_kernel, iterations=2)
    
    # Count actual line pixels
    h_count = cv2.countNonZero(horizontal_lines)
    v_count = cv2.countNonZero(vertical_lines)
    
    # Table must have both horizontal AND vertical lines
    return h_count > 500 and v_count > 500

def preprocess_for_tables(image):
    """Enhance image for better table detection."""
    import cv2
    import numpy as np
    
    img_array = np.array(image)
    gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
    gray = cv2.equalizeHist(gray)
    gray = cv2.fastNlMeansDenoising(gray, h=10)
    binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    return Image.fromarray(binary)

def enhanced_ocr(page_image, lang='eng+heb+ara'):
    """Retry OCR with table-optimized settings only if actual table detected."""
    import pytesseract
    
    # Check if page has actual table structure
    has_table = detect_actual_tables(page_image)
    
    if has_table:
        # Use table preprocessing and preserve spaces
        processed_image = preprocess_for_tables(page_image)
        config = '--psm 6 --oem 1 --preserve-interword-spaces 1'
        logger.info("Table detected, using table-optimized OCR")
    else:
        # Regular text processing without table optimization
        processed_image = page_image
        config = '--psm 6 --oem 1'
        logger.info("No table detected, using standard OCR")
    
    ocr_text = pytesseract.image_to_string(processed_image, lang=lang, config=config)
    ocr_data = pytesseract.image_to_data(processed_image, lang=lang, config='--psm 6 --oem 1', output_type=pytesseract.Output.DICT)
    
    confidences = [int(conf) for conf in ocr_data['conf'] if conf != '-1' and str(conf).isdigit()]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0
    
    return ocr_text, avg_confidence

def extract_images_from_pdf(pdf_path, base_name):
    """Extract embedded images from PDF pages, skipping headers/footers and duplicates."""
    from pypdf import PdfReader
    import fitz  # PyMuPDF
    import hashlib
    
    extracted_images = []
    seen_hashes = set()
    
    try:
        pdf_document = fitz.open(pdf_path)
        total_pages = len(pdf_document)
        
        for page_num in range(total_pages):
            page = pdf_document[page_num]
            page_height = page.rect.height
            image_list = page.get_images(full=True)
            
            for img_index, img in enumerate(image_list):
                xref = img[0]
                
                # Get image position to detect headers/footers
                try:
                    img_rects = [item for item in page.get_image_rects(xref)]
                    if img_rects:
                        img_rect = img_rects[0]
                        img_y = img_rect.y0
                        img_height = img_rect.height
                        
                        # Skip ONLY small images in header/footer zones
                        # Large images (>15% of page height) are kept even if they start in header/footer
                        is_in_header = img_y < page_height * 0.05
                        is_in_footer = img_y > page_height * 0.95
                        is_large_image = img_height > page_height * 0.15
                        
                        if (is_in_header or is_in_footer) and not is_large_image:
                            logger.info(f"Skipping small header/footer image on page {page_num + 1}")
                            continue
                except:
                    pass
                
                base_image = pdf_document.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]
                
                # Skip very small images (likely icons/logos)
                if len(image_bytes) < 10000:  # 10KB minimum
                    continue
                
                # Check for duplicate images using hash
                img_hash = hashlib.md5(image_bytes).hexdigest()
                if img_hash in seen_hashes:
                    logger.info(f"Skipping duplicate image on page {page_num + 1}")
                    continue
                seen_hashes.add(img_hash)
                
                # Convert to JPEG if needed
                if image_ext != "jpeg":
                    try:
                        img_pil = Image.open(io.BytesIO(image_bytes))
                        img_byte_arr = io.BytesIO()
                        img_pil.convert('RGB').save(img_byte_arr, format='JPEG', quality=90)
                        image_bytes = img_byte_arr.getvalue()
                        image_ext = "jpg"
                    except:
                        continue
                
                extracted_images.append({
                    'page': page_num + 1,
                    'index': img_index,
                    'data': image_bytes,
                    'ext': image_ext
                })
        
        pdf_document.close()
        logger.info(f"Extracted {len(extracted_images)} unique images from PDF (skipped duplicates and headers/footers)")
        return extracted_images
        
    except Exception as e:
        logger.error(f"Image extraction failed: {e}")
        return []


def update_progress(base_name, progress, message, status="processing"):
    """Write progress update to S3."""
    if not base_name:
        return
    try:
        s3_client = get_s3_client()
        progress_data = {
            "status": status,
            "progress": progress,
            "message": message,
            "timestamp": int(time.time())
        }
        s3_client.put_object(
            Bucket=BUCKET,
            Key=f"progress/{base_name}.json",
            Body=json.dumps(progress_data),
            ContentType="application/json"
        )
    except Exception as e:
        logger.warning(f"Failed to update progress: {e}")

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
            s3_key = unquote_plus(record["s3"]["object"]["key"])
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
            s3_key = unquote_plus(s3_record["s3"]["object"]["key"])
        
        # Validate S3 key to prevent path traversal and injection attacks
        if not s3_key or '..' in s3_key or s3_key.startswith('/') or '\\' in s3_key:
            logger.error(f"Invalid S3 key detected: path traversal attempt")
            return
        
        # Additional validation for allowed prefixes
        if not s3_key.startswith('uploads/'):
            logger.error(f"S3 key not in allowed uploads prefix")
            return

        logger.info(f"Processing started | Bucket: {s3_bucket} | Key: {s3_key}")
        # Sanitize base_name - use string split to preserve Unicode
        filename = s3_key.split('/')[-1]
        # Use manual split instead of os.path.splitext to preserve Hebrew/Unicode
        if '.' in filename:
            base_name = '.'.join(filename.split('.')[:-1])
        else:
            base_name = filename
        # Remove any remaining path separators
        base_name = base_name.replace('/', '_').replace('\\', '_')
        logger.info(f"File info | Filename: {filename} | BaseName: {base_name}")
        
        # Check if already processed to prevent duplicate processing
        s3_client = get_s3_client()
        try:
            # Get source file timestamp
            source_obj = s3_client.head_object(Bucket=s3_bucket, Key=s3_key)
            source_modified = source_obj['LastModified']
            
            # Get processed marker timestamp
            processed_obj = s3_client.head_object(Bucket=BUCKET, Key=f"processed/{base_name}.json")
            processed_time = processed_obj['LastModified']
            
            # Only skip if source file hasn't been modified since processing
            if source_modified <= processed_time:
                logger.info(f"File already processed and not modified, skipping: {base_name}")
                update_progress(base_name, 100, "Already processed - ready to query!", "completed")
                return
            else:
                logger.info(f"File modified since last processing, reprocessing: {base_name}")
        except s3_client.exceptions.ClientError:
            pass  # Not processed yet or error checking, continue
        
        update_progress(base_name, 5, "Starting document processing...")
        
        # Check cancellation marker
        check_cancelled(base_name)

        with tempfile.TemporaryDirectory() as tmpdir:
            # Secure filename handling to prevent path traversal while preserving Unicode
            safe_filename = os.path.basename(s3_key)
            # Remove only dangerous characters, keep Unicode (Hebrew, Arabic, etc.)
            safe_filename = ''.join(c for c in safe_filename if c not in ['/', '\\', '\0', ':', '*', '?', '"', '<', '>', '|'])
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
                update_progress(base_name, 10, "File downloaded, analyzing content...")
                
                max_size = 100 * 1024 * 1024
                if file_size > max_size:
                    logger.error(f"File too large: {file_size} bytes")
                    raise ValueError(f"File exceeds maximum size of {max_size} bytes")
                    
            except (IOError, OSError) as e:
                logger.error(f"File download failed: {type(e).__name__}")
                raise

            # ---- Document Processing ----
            full_text = ""
            image_metadata = []
            file_ext = s3_key.lower().split('.')[-1]
            
            if file_ext in ['jpg', 'jpeg', 'png', 'tiff']:
                logger.info(f"Processing image file: {file_ext}")
                update_progress(base_name, 20, "Analyzing image...")
                
                # Read image file
                with open(local_path, 'rb') as f:
                    image_data = f.read()
                
                # Analyze image
                try:
                    analysis = analyze_image(image_data)
                    desc_parts = [f"Image file: {base_name}"]
                    if analysis['objects']:
                        desc_parts.append(f"Objects: {', '.join(analysis['objects'])}")
                    if analysis['colors']:
                        desc_parts.append(f"Colors: {', '.join(analysis['colors'])}")
                    description = '. '.join(desc_parts)
                except:
                    description = f"Image file: {base_name}"
                
                # OCR on image
                try:
                    import pytesseract
                    img_pil = Image.open(local_path)
                    ocr_text = pytesseract.image_to_string(img_pil, lang='eng+heb+ara', config='--psm 3 --oem 1')
                    if ocr_text.strip():
                        full_text = f"Image text content:\n{ocr_text}"
                        description += f"\nText: {ocr_text.strip()[:100]}"
                except:
                    full_text = f"Image: {base_name}"
                
                # Save image to S3
                img_name = f"{base_name}.{file_ext}"
                img_key = f"images/{base_name}/{img_name}"
                s3_client.put_object(
                    Bucket=BUCKET,
                    Key=img_key,
                    Body=image_data,
                    ContentType=f'image/{"jpeg" if file_ext in ["jpg", "jpeg"] else file_ext}'
                )
                
                image_metadata.append({
                    'page': 1,
                    'image_name': img_name,
                    's3_key': img_key,
                    'url': f"https://{BUCKET}.s3.amazonaws.com/{img_key}",
                    'description': description
                })
                
                logger.info(f"Image processing complete | Description: {description[:100]}")
            
            elif file_ext == 'pptx':
                logger.info("Processing PowerPoint file")
                update_progress(base_name, 20, "Extracting PowerPoint content...")
                full_text, extracted_images = extract_pptx(local_path)
                
                # Save extracted images - NO FILTERING, keep all images with sequential numbering
                for img_info in extracted_images:
                    img_name = f"{base_name}_slide{img_info['page']}_img{img_info['index']}.{img_info['ext']}"
                    img_key = f"images/{base_name}/{img_name}"
                    diagram_type = None
                    is_logo = False
                    ocr_kw = []
                    
                    try:
                        analysis = analyze_image(img_info['data'])
                        diagram_type = analysis.get('diagram_type')
                        is_logo = analysis.get('is_logo_or_banner', False)
                        ocr_kw = analysis.get('ocr_keywords', [])
                        desc_parts = [f"Slide {img_info['page']}"]
                        if diagram_type:
                            desc_parts.append(f"Type: {diagram_type}")
                        if analysis['objects']:
                            desc_parts.append(f"Objects: {', '.join(analysis['objects'])}")
                        if analysis['colors']:
                            desc_parts.append(f"Colors: {', '.join(analysis['colors'])}")
                        description = f"Image from {base_name}. {'. '.join(desc_parts)}"
                    except:
                        description = f"Image from {base_name}, slide {img_info['page']}"
                    
                    s3_client.put_object(
                        Bucket=BUCKET,
                        Key=img_key,
                        Body=img_info['data'],
                        ContentType='image/jpeg'
                    )
                    
                    image_metadata.append({
                        'page': img_info['page'],
                        'image_name': img_name,
                        's3_key': img_key,
                        'url': f"https://{BUCKET}.s3.amazonaws.com/{img_key}",
                        'description': description,
                        'diagram_type': diagram_type,
                        'is_logo_or_banner': is_logo,
                        'ocr_keywords': ocr_kw
                    })
                
                logger.info(f"PPTX processing complete | Text: {len(full_text)} chars | Images: {len(image_metadata)}")
            
            elif file_ext == 'docx':
                logger.info("Processing Word document")
                update_progress(base_name, 20, "Extracting Word document content...")
                full_text, extracted_images = extract_docx(local_path)
                
                # Save extracted images (no page numbers for DOCX)
                for img_idx, img_info in enumerate(extracted_images, 1):
                    img_name = f"{base_name}_img{img_idx-1}.{img_info['ext']}"
                    img_key = f"images/{base_name}/{img_name}"
                    
                    print(f"[WORKER] Processing DOCX image #{img_idx}, size={len(img_info['data'])} bytes")
                    logger.info(f"Processing DOCX image #{img_idx}")
                    diagram_type = None
                    is_logo = False
                    ocr_kw = []
                    try:
                        analysis = analyze_image(img_info['data'])
                        print(f"[WORKER] analyze_image returned: {analysis}")
                        diagram_type = analysis.get('diagram_type')
                        is_logo = analysis.get('is_logo_or_banner', False)
                        ocr_kw = analysis.get('ocr_keywords', [])
                        desc_parts = ["Document image"]
                        if diagram_type:
                            desc_parts.append(f"Type: {diagram_type}")
                        if analysis['objects']:
                            desc_parts.append(f"Objects: {', '.join(analysis['objects'])}")
                        if analysis['colors']:
                            desc_parts.append(f"Colors: {', '.join(analysis['colors'])}")
                        description = f"Image from {base_name}. {'. '.join(desc_parts)}"
                        logger.info(f"Analyzed DOCX image #{img_idx}: diagram_type={diagram_type}, ocr_keywords={ocr_kw}")
                    except Exception as e:
                        print(f"[WORKER] analyze_image FAILED: {e}")
                        logger.error(f"analyze_image failed: {e}")
                        description = f"Image from {base_name}"
                    
                    s3_client.put_object(
                        Bucket=BUCKET,
                        Key=img_key,
                        Body=img_info['data'],
                        ContentType='image/jpeg'
                    )
                    
                    image_metadata.append({
                        'page': None,
                        'image_name': img_name,
                        's3_key': img_key,
                        'url': f"https://{BUCKET}.s3.amazonaws.com/{img_key}",
                        'description': description,
                        'diagram_type': diagram_type,
                        'is_logo_or_banner': is_logo,
                        'ocr_keywords': ocr_kw
                    })
                
                logger.info(f"DOCX processing complete | Text: {len(full_text)} chars | Images: {len(image_metadata)}")
            
            elif file_ext == 'xlsx':
                logger.info("Processing Excel spreadsheet")
                update_progress(base_name, 20, "Extracting Excel data...")
                full_text, _ = extract_xlsx(local_path)
                logger.info(f"XLSX processing complete | Text: {len(full_text)} chars")
            
            elif file_ext == 'pdf':
                try:
                    # Check PDF page count for chunking decision
                    from pypdf import PdfReader
                    reader = PdfReader(local_path)
                    total_pdf_pages = len(reader.pages)
                    logger.info(f"PDF has {total_pdf_pages} pages")
                    
                    # If PDF is too large (>60 pages), process in chunks to avoid timeout
                    if total_pdf_pages > 60:
                        logger.info(f"Large PDF detected ({total_pdf_pages} pages), processing in chunks")
                        update_progress(base_name, 10, f"Processing large PDF ({total_pdf_pages} pages) in chunks...")
                        
                        # Split into chunks of 30 pages for better memory management
                        chunk_size = 30
                        num_chunks = (total_pdf_pages + chunk_size - 1) // chunk_size
                        
                        all_text_parts = []
                        all_images = []
                        
                        for chunk_idx in range(num_chunks):
                            start_page = chunk_idx * chunk_size
                            end_page = min(start_page + chunk_size, total_pdf_pages)
                            
                            chunk_progress = 10 + int((chunk_idx / num_chunks) * 70)
                            update_progress(base_name, chunk_progress, f"Processing pages {start_page+1}-{end_page} of {total_pdf_pages}...")
                            logger.info(f"Processing chunk {chunk_idx+1}/{num_chunks}: pages {start_page+1}-{end_page}")
                            
                            # Convert only this chunk's pages
                            chunk_images = convert_from_path(local_path, dpi=150, first_page=start_page+1, last_page=end_page)
                            
                            for page_num, page_image in enumerate(chunk_images, start=start_page+1):
                                # Update progress for each page
                                page_progress = 10 + int(((page_num - 1) / total_pdf_pages) * 70)
                                update_progress(base_name, page_progress, f"OCR processing page {page_num}/{total_pdf_pages}...")
                                logger.info(f"Progress update: {page_progress}% - Page {page_num}/{total_pdf_pages}")
                                
                                # Check cancellation every 5 pages
                                if page_num % 5 == 0:
                                    check_cancelled(base_name)
                                
                                try:
                                    import pytesseract
                                    # Detect if page has actual table
                                    has_table = detect_actual_tables(page_image)
                                    config = '--psm 6 --oem 1 --preserve-interword-spaces 1' if has_table else '--psm 6 --oem 1'
                                    logger.info(f"Page {page_num}: {'Table detected' if has_table else 'No table detected'}")
                                    
                                    ocr_text = pytesseract.image_to_string(page_image, lang='eng+heb+ara', config=config)
                                    ocr_data = pytesseract.image_to_data(page_image, lang='eng+heb+ara', config='--psm 6 --oem 1', output_type=pytesseract.Output.DICT)
                                    confidences = [int(conf) for conf in ocr_data['conf'] if conf != '-1' and str(conf).isdigit()]
                                    
                                    avg_confidence = 0
                                    if confidences:
                                        avg_confidence = sum(confidences) / len(confidences)
                                        logger.info(f"Page {page_num} OCR confidence: {avg_confidence:.1f}%")
                                    
                                    if avg_confidence < 70 and avg_confidence > 0:
                                        logger.info(f"Page {page_num}: Low confidence ({avg_confidence:.1f}%), retrying with PSM 6")
                                        ocr_text, avg_confidence = enhanced_ocr(page_image)
                                        logger.info(f"Page {page_num}: PSM 6 confidence: {avg_confidence:.1f}%")
                                    
                                    logger.info(f"Page {page_num}: Final confidence {avg_confidence:.1f}%")
                                    
                                    if ocr_text.strip():
                                        all_text_parts.append(f"\n[PAGE {page_num} TEXT]:\n{ocr_text}\n")
                                        logger.info(f"Page {page_num} OCR: {len(ocr_text)} chars")
                                except Exception as ocr_e:
                                    logger.warning(f"Page {page_num} OCR failed: {ocr_e}")
                                
                                page_image.close()
                        
                        full_text = ''.join(all_text_parts)
                        logger.info(f"Chunked processing complete | Total pages: {total_pdf_pages} | Text: {len(full_text)} chars")
                        
                        # Extract images from full PDF (images are quick)
                        embedded_images = extract_images_from_pdf(local_path, base_name)
                        for img_info in embedded_images:
                            img_name = f"{base_name}_page{img_info['page']}_img{img_info['index']}.{img_info['ext']}"
                            img_key = f"images/{base_name}/{img_name}"
                            diagram_type = None
                            is_logo = False
                            ocr_kw = []
                            try:
                                analysis = analyze_image(img_info['data'])
                                diagram_type = analysis.get('diagram_type')
                                is_logo = analysis.get('is_logo_or_banner', False)
                                ocr_kw = analysis.get('ocr_keywords', [])
                                desc_parts = [f"Page {img_info['page']}"]
                                if diagram_type:
                                    desc_parts.append(f"Type: {diagram_type}")
                                if analysis['objects']:
                                    desc_parts.append(f"Objects: {', '.join(analysis['objects'])}")
                                if analysis['colors']:
                                    desc_parts.append(f"Colors: {', '.join(analysis['colors'])}")
                                
                                # Add OCR text from image
                                try:
                                    import pytesseract
                                    img_pil = Image.open(io.BytesIO(img_info['data']))
                                    img_text = pytesseract.image_to_string(img_pil, lang='eng+heb+ara', config='--psm 3 --oem 1')
                                    if img_text.strip():
                                        desc_parts.append(f"Text: {img_text.strip()[:50]}")
                                except:
                                    pass
                                
                                description = f"Image from {base_name}. {'. '.join(desc_parts)}"
                                logger.info(f"Analyzed image page {img_info['page']}: diagram_type={diagram_type}")
                            except:
                                description = f"Image from {base_name}, page {img_info['page']}"
                            
                            s3_client.put_object(Bucket=BUCKET, Key=img_key, Body=img_info['data'], ContentType='image/jpeg')
                            image_metadata.append({
                                'page': img_info['page'],
                                'image_name': img_name,
                                's3_key': img_key,
                                'url': f"https://{BUCKET}.s3.amazonaws.com/{img_key}",
                                'description': description,
                                'diagram_type': diagram_type,
                                'is_logo_or_banner': is_logo,
                                'ocr_keywords': ocr_kw
                            })
                    else:
                        # Original processing for smaller PDFs
                        logger.info(f"Standard PDF processing for {total_pdf_pages} pages")
                        # FIRST: Extract embedded images from PDF
                        logger.info(f"Extracting embedded images from PDF")
                        update_progress(base_name, 15, "Extracting images from PDF...")
                        embedded_images = extract_images_from_pdf(local_path, base_name)
                        
                        # Process embedded images with basic descriptions
                        for img_info in embedded_images:
                            img_name = f"{base_name}_page{img_info['page']}_img{img_info['index']}.{img_info['ext']}"
                            img_key = f"images/{base_name}/{img_name}"
                            diagram_type = None
                            is_logo = False
                            
                            # Analyze image with color and object detection
                            try:
                                analysis = analyze_image(img_info['data'])
                                diagram_type = analysis.get('diagram_type')
                                is_logo = analysis.get('is_logo_or_banner', False)
                                
                                desc_parts = [f"Page {img_info['page']}"]
                                if diagram_type:
                                    desc_parts.append(f"Type: {diagram_type}")
                                if analysis['objects']:
                                    desc_parts.append(f"Objects: {', '.join(analysis['objects'])}")
                                if analysis['colors']:
                                    desc_parts.append(f"Colors: {', '.join(analysis['colors'])}")
                                
                                # Add OCR text
                                try:
                                    import pytesseract
                                    img_pil = Image.open(io.BytesIO(img_info['data']))
                                    img_text = pytesseract.image_to_string(img_pil, lang='eng+heb+ara', config='--psm 3 --oem 1')
                                    if img_text.strip():
                                        desc_parts.append(f"Text: {img_text.strip()[:50]}")
                                except:
                                    pass
                                
                                description = f"Image from {base_name}. {'. '.join(desc_parts)}"
                                logger.info(f"Analyzed image page {img_info['page']}: diagram_type={diagram_type}")
                            except Exception as e:
                                logger.warning(f"Image analysis failed: {e}")
                                description = f"Image from {base_name}, page {img_info['page']}"
                            
                            # Save image to S3
                            s3_client = get_s3_client()
                            s3_client.put_object(
                                Bucket=BUCKET,
                                Key=img_key,
                                Body=img_info['data'],
                                ContentType='image/jpeg'
                            )
                            
                            image_metadata.append({
                                'page': img_info['page'],
                                'image_name': img_name,
                                's3_key': img_key,
                                'url': f"https://{BUCKET}.s3.amazonaws.com/{img_key}",
                                'description': description,
                                'diagram_type': diagram_type,
                                'is_logo_or_banner': is_logo,
                                'ocr_keywords': analysis.get('ocr_keywords', [])
                            })
                            logger.info(f"Saved image from page {img_info['page']}: {description[:80]}...")
                        
                        # SECOND: Process text with Tesseract OCR only
                        logger.info(f"Processing text with Tesseract OCR")
                        all_page_images = convert_from_path(local_path, dpi=150)
                        total_pages = len(all_page_images)
                        update_progress(base_name, 30, f"Running OCR on {total_pages} pages...")
                        
                        for page_num, page_image in enumerate(all_page_images, 1):
                            ocr_progress = 30 + int((page_num / total_pages) * 40)
                            update_progress(base_name, ocr_progress, f"OCR processing page {page_num}/{total_pages}...")
                            logger.info(f"Progress update: {ocr_progress}% - Page {page_num}/{total_pages}")
                            # Check cancellation every 5 pages
                            if page_num % 5 == 0:
                                check_cancelled(base_name)
                            
                            # Tesseract OCR with table detection
                            logger.info(f"Page {page_num}: Tesseract OCR")
                            try:
                                import pytesseract
                                # Detect if page has actual table
                                has_table = detect_actual_tables(page_image)
                                config = '--psm 6 --oem 1 --preserve-interword-spaces 1' if has_table else '--psm 6 --oem 1'
                                logger.info(f"Page {page_num}: {'Table detected' if has_table else 'No table detected'}")
                                
                                ocr_text = pytesseract.image_to_string(
                                    page_image, 
                                    lang='eng+heb+ara', 
                                    config=config
                                )
                                
                                ocr_data = pytesseract.image_to_data(page_image, lang='eng+heb+ara', config='--psm 6 --oem 1', output_type=pytesseract.Output.DICT)
                                confidences = [int(conf) for conf in ocr_data['conf'] if conf != '-1' and str(conf).isdigit()]
                                
                                avg_confidence = 0
                                if confidences:
                                    avg_confidence = sum(confidences) / len(confidences)
                                    logger.info(f"Page {page_num} OCR confidence: {avg_confidence:.1f}%")
                                
                                # If confidence is very low, retry with different PSM mode
                                if avg_confidence < 70 and avg_confidence > 0:
                                    logger.info(f"Page {page_num}: Low confidence ({avg_confidence:.1f}%), retrying with PSM 6...")
                                    enhanced_text, enhanced_confidence = enhanced_ocr(page_image)
                                    if enhanced_confidence > avg_confidence:
                                        logger.info(f"Page {page_num}: PSM 6 improved confidence to {enhanced_confidence:.1f}%")
                                        ocr_text = enhanced_text
                                        avg_confidence = enhanced_confidence
                                
                                logger.info(f"Page {page_num}: Final confidence {avg_confidence:.1f}%")
                                
                                if ocr_text.strip():
                                    # Add English translation for non-Latin text to improve cross-language search
                                    has_non_latin = any(ord(c) > 127 for c in ocr_text)
                                    if has_non_latin:
                                        try:
                                            bedrock = get_bedrock_client()
                                            translate_body = {
                                                "anthropic_version": "bedrock-2023-05-31",
                                                "max_tokens": 2000,
                                                "messages": [{"role": "user", "content": f"Translate this text to English. Keep technical terms, numbers, and specifications exact. Only translate, don't summarize:\n\n{ocr_text[:1500]}"}]
                                            }
                                            response = bedrock.invoke_model(modelId="anthropic.claude-3-haiku-20240307-v1:0", body=json.dumps(translate_body))
                                            translation = json.loads(response['body'].read())['content'][0]['text']
                                            full_text += f"\n[PAGE {page_num} TEXT]:\n{ocr_text}\n[PAGE {page_num} ENGLISH]:\n{translation}\n"
                                            logger.info(f"Page {page_num} OCR: {len(ocr_text)} chars + translation")
                                        except Exception as trans_e:
                                            logger.warning(f"Translation failed: {trans_e}")
                                            full_text += f"\n[PAGE {page_num} TEXT]:\n{ocr_text}\n"
                                            logger.info(f"Page {page_num} OCR: {len(ocr_text)} chars")
                                    else:
                                        full_text += f"\n[PAGE {page_num} TEXT]:\n{ocr_text}\n"
                                        logger.info(f"Page {page_num} OCR: {len(ocr_text)} chars")
                            except Exception as ocr_e:
                                logger.warning(f"Page {page_num} Tesseract failed: {ocr_e}")
                            
                            page_image.close()
                        
                        logger.info(f"Hybrid processing complete | Pages: {len(all_page_images)} | Images: {len(image_metadata)}")
                    
                except Exception as e:
                    logger.error(f"PDF processing failed: {e}")
                    # Fallback to pypdf
                    try:
                        from pypdf import PdfReader
                        reader = PdfReader(local_path)
                        for page in reader.pages:
                            text = page.extract_text() or ""
                            if text.strip():
                                full_text += text + "\n"
                        logger.info(f"Fallback extraction: {len(full_text)} chars")
                    except Exception as fallback_e:
                        logger.error(f"All extraction failed: {fallback_e}")
                        full_text = f"Document: {base_name} - Processing failed"
            else:
                logger.warning(f"Unsupported file type: {file_ext}")
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
            doc_name = base_name
            update_progress(base_name, 75, "Creating searchable chunks...")
            
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
                            "source": base_name,
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
                logger.info(f"DEBUG: Creating FAISS documents for {len(image_metadata)} images")
                for idx, img_meta in enumerate(image_metadata, 1):
                    ocr_kw_debug = img_meta.get('ocr_keywords', [])
                    logger.info(f"DEBUG: Image #{idx} ocr_keywords from image_metadata: {ocr_kw_debug}")
                    description = img_meta.get('description', 'Image content')
                    
                    color_keywords = []
                    if 'PRIMARY_COLOR:' in description:
                        primary_color = description.split('PRIMARY_COLOR:')[1].split('\n')[0].strip()
                        if primary_color and primary_color.lower() != 'none':
                            color_keywords.append(primary_color.lower())
                    
                    # Make image number VERY prominent for better search matching
                    if img_meta['page'] is not None:
                        searchable_content = f"Document: {doc_name}\nIMAGE NUMBER {idx} | Image #{idx} | Image number {idx} | תמונה מספר {idx}\nPage {img_meta['page']}: {description}\nIMAGE_URL:{img_meta['s3_key']}|PAGE:{img_meta['page']}|SOURCE:{doc_name}"
                    else:
                        searchable_content = f"Document: {doc_name}\nIMAGE NUMBER {idx} | Image #{idx} | Image number {idx} | תמונה מספר {idx}\n{description}\nIMAGE_URL:{img_meta['s3_key']}|SOURCE:{doc_name}"
                    
                    if color_keywords:
                        searchable_content += f"\nColor tags: {' '.join(color_keywords)}"
                    
                    img_doc = Document(
                        page_content=searchable_content,
                        metadata={
                            "source": base_name,
                            "type": "image",
                            "page": img_meta['page'],
                            "image_number": idx,
                            "image_url": img_meta['url'],
                            "s3_key": img_meta['s3_key'],
                            "description": description,
                            "diagram_type": img_meta.get('diagram_type'),
                            "is_logo_or_banner": img_meta.get('is_logo_or_banner', False),
                            "ocr_keywords": img_meta.get('ocr_keywords', [])
                        }
                    )
                    docs.append(img_doc)
                    logger.info(f"Added image #{idx}: {description[:50]}...")
            
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
            # Initialize fallback splitter once
            from langchain.text_splitter import RecursiveCharacterTextSplitter
            safe_splitter = RecursiveCharacterTextSplitter(chunk_size=1800, chunk_overlap=100)

            for doc in docs:
                content = doc.page_content.strip()
                # IF content is safe size, keep it
                if content and len(content) <= 2000:
                    valid_docs.append(doc)
                # IF content is too big, split it safely instead of truncating
                elif content:
                    logger.warning(f"Chunk too large ({len(content)} chars), splitting safely to prevent data loss.")
                    safe_chunks = safe_splitter.split_text(content)
                    for i, safe_chunk in enumerate(safe_chunks):
                        # Create new document for each sub-chunk preserving original metadata
                        new_metadata = doc.metadata.copy()
                        new_metadata.update({
                            'original_chunk_id': doc.metadata.get('chunk_id'),
                            'split_part': i,
                            'is_fallback_split': True
                        })
                        valid_docs.append(Document(page_content=safe_chunk, metadata=new_metadata))
            
            if not valid_docs:
                logger.error("No valid documents for embedding")
                raise ValueError("No valid documents to embed")
            
            logger.info(f"Embedding {len(valid_docs)} valid documents (filtered from {len(docs)})")
            update_progress(base_name, 85, "Creating AI embeddings...")
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
            update_progress(base_name, 95, "Finalizing and saving index...")
            try:
                s3_client.upload_file(master_index_path, BUCKET, "vector_store/master/index.faiss")
                s3_client.upload_file(master_pkl_path, BUCKET, "vector_store/master/index.pkl")
                logger.info(f"Master index uploaded | Bucket: {BUCKET} | Time: {time.time() - upload_start:.2f}s")
            except Exception as e:
                logger.error(f"Master index upload failed | Error: {type(e).__name__} | Details: {str(e)[:100]}")
                raise

            # Mark as processed - add image_number to each image in metadata
            for idx, img_meta in enumerate(image_metadata, 1):
                img_meta['image_number'] = idx
            
            # Add timestamp prefix to match frontend expectations
            timestamp = int(time.time())
            marker_key = f"processed/{timestamp}_{base_name}.json"
            marker_content = {
                "source_file": s3_key,
                "status": "processed",
                "images": image_metadata,
                "text_chunks": len(docs) - len(image_metadata),
                "full_text": full_text if full_text else "No text extracted",
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
            update_progress(base_name, 100, "Complete!", "completed")

    except ProcessingCancelled as e:
        logger.info(f"Processing cancelled | File: {base_name} | Time: {time.time() - start_time:.2f}s")
        update_progress(base_name, 0, "Cancelled by user", "failed")
        return
    except (ValueError, IOError, OSError) as e:
        logger.error(f"Processing failed | File: {base_name} | Error: {type(e).__name__} | Details: {str(e)[:100]} | Time: {time.time() - start_time:.2f}s")
        update_progress(base_name, 0, f"Error: {type(e).__name__}", "failed")
        raise
    except Exception as e:
        logger.error(f"Unexpected error | File: {base_name} | Error: {type(e).__name__} | Details: {str(e)[:200]} | Time: {time.time() - start_time:.2f}s")
        update_progress(base_name, 0, f"Error: {type(e).__name__}", "failed")
        raise
