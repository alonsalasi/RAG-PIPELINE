import os
import io
import json
import boto3
import tempfile
import logging
import numpy as np
import base64
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

BUCKET = os.environ.get("S3_BUCKET", "pdfquery-rag-documents-default")

def process_message(record):
    try:
        # Extract S3 info from SQS record
        body = record.get("body")
        if not body:
            logger.warning("⚠️ Empty SQS body, skipping.")
            return

        # Parse the SNS message from SQS
        s3_event = json.loads(body)
        s3_record = s3_event["Records"][0]
        s3_bucket = s3_record["s3"]["bucket"]["name"]
        s3_key = s3_record["s3"]["object"]["key"]

        logger.info(f"📥 Processing file: s3://{s3_bucket}/{s3_key}")

        with tempfile.TemporaryDirectory() as tmpdir:
            local_path = os.path.join(tmpdir, os.path.basename(s3_key))
            s3.download_file(s3_bucket, s3_key, local_path)
            logger.info(f"✅ Downloaded {os.path.getsize(local_path)} bytes to {local_path}")

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
                                        
                                        # Save image to S3
                                        img_name = f"{base_name}_page{page_num}_img{len(image_metadata)}.jpg"
                                        img_key = f"images/{base_name}/{img_name}"
                                        
                                        s3.put_object(
                                            Bucket=BUCKET,
                                            Key=img_key,
                                            Body=img_data,
                                            ContentType='image/jpeg'
                                        )
                                        
                                        image_metadata.append({
                                            'page': page_num,
                                            'image_name': img_name,
                                            's3_key': img_key,
                                            'url': f"https://{BUCKET}.s3.amazonaws.com/{img_key}"
                                        })
                                        logger.info(f"✅ Extracted image from page {page_num}: {img_key}")
                                    except Exception as img_e:
                                        logger.warning(f"Failed to extract image: {img_e}")
                    
                    logger.info(f"📸 Extracted {len(image_metadata)} images from PDF")
                except Exception as e:
                    logger.warning(f"Image extraction failed: {e}")
            
            # ---- OCR-based text extraction ----
            full_text = ""
            base_name = os.path.splitext(os.path.basename(s3_key))[0]
            
            if s3_key.lower().endswith('.pdf'):
                try:
                    # First try pypdf for text-based PDFs
                    from pypdf import PdfReader
                    reader = PdfReader(local_path)
                    for i, page in enumerate(reader.pages, 1):
                        text = page.extract_text() or ""
                        if text.strip() and len(text.strip()) > 50:  # If we get substantial text
                            logger.info(f"✅ Page {i} extracted via pypdf: {len(text)} chars")
                            full_text += text + "\n"
                        else:
                            logger.info(f"⚠️ Page {i} has minimal text, using OCR")
                            # Use OCR for this page
                            try:
                                from pdf2image import convert_from_path
                                import io as iolib
                                
                                # Convert just this page to image
                                images = convert_from_path(local_path, first_page=i, last_page=i, dpi=200)
                                if images:
                                    import pytesseract
                                    
                                    # Quick test with fast OCR to check quality
                                    test_data = pytesseract.image_to_data(images[0], lang='heb+eng+tur', output_type=pytesseract.Output.DICT)
                                    confidences = [int(c) for c in test_data['conf'] if c != '-1' and str(c).isdigit()]
                                    avg_confidence = sum(confidences) / len(confidences) if confidences else 100
                                    
                                    # If high confidence (>70), use fast OCR. If low, use preprocessing
                                    if avg_confidence > 70:
                                        # Fast path for printed text
                                        ocr_text = pytesseract.image_to_string(images[0], lang='heb+eng+tur')
                                        logger.info(f"✅ Page {i} Fast OCR (conf={avg_confidence:.1f}): {len(ocr_text)} chars")
                                    else:
                                        # Slow path with preprocessing for handwritten/low quality
                                        logger.info(f"🔍 Page {i} Low confidence ({avg_confidence:.1f}), using enhanced OCR")
                                        from PIL import ImageEnhance, ImageFilter, Image
                                        import cv2
                                        
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
                                        
                                        ocr_text = pytesseract.image_to_string(img, lang='heb+eng+tur', config='--psm 3 --oem 1')
                                        logger.info(f"✅ Page {i} Enhanced OCR extracted: {len(ocr_text)} chars")
                                    
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
                logger.warning(f"⚠️ Insufficient text extracted ({len(full_text)} chars); skipping embedding.")
                return

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
                    img_doc = Document(
                        page_content=f"Image on page {img_meta['page']} of {os.path.basename(s3_key)}",
                        metadata={
                            "source": os.path.basename(s3_key),
                            "type": "image",
                            "page": img_meta['page'],
                            "image_url": img_meta['url'],
                            "s3_key": img_meta['s3_key']
                        }
                    )
                    docs.append(img_doc)
            
            logger.info(f"📝 Created {len(docs)} chunks")

            # ---- Create FAISS index per file ----
            embed = BedrockEmbeddings(model_id="amazon.titan-embed-text-v1", region_name=os.environ.get("AWS_REGION", "us-east-1"))
            logger.info("🔍 Building FAISS index...")
            store = FAISS.from_documents(docs, embed)

            # ---- Save index with filename ----
            base_name = os.path.splitext(os.path.basename(s3_key))[0]
            store.save_local(tmpdir)
            
            index_path = os.path.join(tmpdir, "index.faiss")
            pkl_path = os.path.join(tmpdir, "index.pkl")
            
            s3.upload_file(index_path, BUCKET, f"vector_store/{base_name}/index.faiss")
            s3.upload_file(pkl_path, BUCKET, f"vector_store/{base_name}/index.pkl")
            logger.info(f"✅ Uploaded FAISS index to s3://{BUCKET}/vector_store/{base_name}/")

            # ---- Mark as processed ----
            marker_key = f"processed/{base_name}.json"
            marker_content = {
                "source_file": s3_key,
                "status": "processed",
                "images": image_metadata
            }
            
            s3.put_object(
                Bucket=BUCKET,
                Key=marker_key,
                Body=json.dumps(marker_content),
                ContentType="application/json"
            )
            logger.info(f"✅ Marker written to s3://{BUCKET}/{marker_key}")

    except Exception as e:
        logger.error(f"🚨 Failed processing record: {e}")
        raise e
