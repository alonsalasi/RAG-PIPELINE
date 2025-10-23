import os
import json
import boto3
import fitz # PyMuPDF
import pytesseract
from PIL import Image
from io import BytesIO
from urllib.parse import urlparse
import subprocess
import traceback # Added for detailed error logging

# Optional fallback
try:
    from pdf2image import convert_from_bytes
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False

# --- Configuration ---
S3_DOCUMENTS_BUCKET = os.environ.get("S3_DOCUMENTS_BUCKET")
AWS_REGION = os.environ.get("AWS_REGION", "us-west-2")

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

# --- AWS Clients ---
s3_client = boto3.client("s3", region_name=AWS_REGION)

# --- LangChain Text Splitter ---
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n\n", "\n", " ", ""],
)

# --- Ensure Tesseract path ---
pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"

# --- Debug: Print Tesseract version and available languages ---
try:
    version = subprocess.check_output(
        [pytesseract.pytesseract.tesseract_cmd, "--version"]
    ).decode()
    print("DEBUG: Tesseract version:\n", version.strip())
    
    langs = subprocess.check_output(
        [pytesseract.pytesseract.tesseract_cmd, "--list-langs"]
    ).decode()
    print("DEBUG: Tesseract languages:\n", langs.strip())
except Exception as e:
    print(f"WARNING: Could not check Tesseract version or languages: {e}")


# ======================================================================
# OCR + Text Extraction Logic
# ======================================================================
def extract_text_with_tesseract(bucket, key):
    print(f"DEBUG: Downloading s3://{bucket}/{key} ...")
    response = s3_client.get_object(Bucket=bucket, Key=key)
    file_bytes = response["Body"].read()
    print(f"DEBUG: File downloaded. Size: {len(file_bytes)} bytes.")

    text_output = ""
    pdf_processed = False

    # --- Try with PyMuPDF first (OCR on each page) ---
    try:
        pdf_doc = fitz.open(stream=file_bytes, filetype="pdf")
        num_pages = len(pdf_doc)
        print(f"File identified as PDF. Processing {num_pages} pages...")
        pdf_processed = True

        for page_num in range(num_pages):
            page = pdf_doc.load_page(page_num)
            
            # Rendering to high-DPI pixmap
            print(f"DEBUG: Page {page_num+1}/{num_pages} - Rendering to 300 DPI pixmap...")
            pix = page.get_pixmap(dpi=300, alpha=False)
            
            # CRITICAL FIX: Save pixmap to /tmp and pass the file path to Tesseract
            # This is the most stable method on AWS Lambda
            temp_path = f"/tmp/{os.path.basename(key)}-page-{page_num}.png"
            
            print(f"DEBUG: Page {page_num+1} - Saving pixmap to temporary file: {temp_path}")
            
            try:
                # MuPDF's save method is highly reliable
                pix.save(temp_path)
            except Exception as e:
                print(f"CRITICAL ERROR: PyMuPDF failed to save pixmap to /tmp. Error: {e}")
                raise e

            print(f"DEBUG: Page {page_num+1} - Running Tesseract on temporary file...")
            
            # Run Tesseract on the physical file path
            page_text = pytesseract.image_to_string(temp_path, lang="heb+eng")
            
            text_output += page_text + "\n\n"
            
            # Clean up the temporary file immediately
            os.remove(temp_path) 
            print(f"DEBUG: Page {page_num+1} - Temp file cleaned up.")
            
        pdf_doc.close()

    except Exception as e:
        # Detailed traceback for failure inside PyMuPDF block
        print(f"WARNING: PyMuPDF/Tesseract (Page-by-page OCR) failed. Traceback:")
        traceback.print_exc()
        print(f"ERROR DETAIL: {e}. Falling back.")
        text_output = ""
        pdf_processed = False

    # --- Check for success after PyMuPDF OCR ---
    if pdf_processed and text_output.strip():
        print(f"DEBUG: PyMuPDF/OCR successful. Extracted {len(text_output)} chars.")
        return text_output

    print("DEBUG: Starting fallback methods...")

    # --- Fallback to pdf2image if available (uses Poppler) ---
    if PDF2IMAGE_AVAILABLE:
        try:
            print("DEBUG: Trying pdf2image fallback (requires Poppler)...")
            images = convert_from_bytes(file_bytes, dpi=300)
            for idx, img in enumerate(images):
                page_text = pytesseract.image_to_string(img, lang="heb+eng")
                text_output += page_text + "\n\n"
            
            if text_output.strip():
                print(f"DEBUG: pdf2image/OCR successful. Extracted {len(text_output)} chars.")
                return text_output
            else:
                print("WARNING: pdf2image returned empty text.")

        except Exception as e:
            print(f"ERROR: pdf2image fallback failed. Traceback:")
            traceback.print_exc()
            text_output = ""

    # --- Final fallback: treat file as a standard image ---
    try:
        print("DEBUG: Trying final fallback: treating file as standard image...")
        
        # This is where the original "cannot identify image file" error occurs
        img = Image.open(BytesIO(file_bytes))
        print(f"DEBUG: PIL successfully opened file as image. Format: {img.format}, Size: {img.size}")
        
        text_output = pytesseract.image_to_string(img, lang="heb+eng")
        
        if text_output.strip():
            print(f"DEBUG: Final fallback successful. Extracted {len(text_output)} chars.")
            return text_output
        else:
            print("WARNING: Final fallback returned empty text.")

    except Exception as e:
        print(f"CRITICAL: Final fallback failed. File is not a readable PDF or a valid image. Traceback:")
        traceback.print_exc()
        raise RuntimeError(f"TESSERACT FAILURE processing {key}: {e}")

    # If all methods fail to produce text
    raise Exception(f"CRITICAL TESSERACT FAILURE processing {key}: No text extracted from document.")


# ======================================================================
# Message Processor
# ======================================================================
def process_message(message_body):
    """Parses SNS/SQS event JSON and extracts + chunks text."""
    try:
        sns_msg = json.loads(message_body)
        s3_event = json.loads(sns_msg.get("Message", "{}"))
        record = s3_event["Records"][0]["s3"]
        bucket = record["bucket"]["name"]
        key = urlparse(record["object"]["key"]).path.lstrip("/")
        print(f"DEBUG: Processing s3://{bucket}/{key}")
        
    except Exception as e:
        print(f"ERROR: Invalid event format. Payload: {message_body}. Error: {e}")
        return False

    try:
        raw_text = extract_text_with_tesseract(bucket, key)
        print(f"DEBUG: Extracted {len(raw_text)} characters.")
    except Exception as e:
        print(f"CRITICAL: OCR extraction failed for {key}: {e}")
        return False

    if not raw_text.strip():
        print(f"WARNING: No text found in {key}, deleting original.")
        try:
            s3_client.delete_object(Bucket=bucket, Key=key)
            print(f"DEBUG: Deleted original s3://{bucket}/{key}")
        except Exception as e:
            print(f"WARNING: Failed to delete empty file {key}: {e}")
        return True

    # --- Chunking and Upload ---
    try:
        docs = [Document(page_content=raw_text, metadata={"source_key": key})]
        chunks = text_splitter.split_documents(docs)
        output_key = f"processed_chunks/{key}.json"

        serialized = [
            {"page_content": c.page_content, "metadata": c.metadata} for c in chunks
        ]

        s3_client.put_object(
            Bucket=S3_DOCUMENTS_BUCKET,
            Key=output_key,
            Body=json.dumps(serialized, ensure_ascii=False),
            ContentType="application/json",
        )
        print(f"SUCCESS: Uploaded {len(chunks)} chunks to s3://{S3_DOCUMENTS_BUCKET}/{output_key}")

        s3_client.delete_object(Bucket=bucket, Key=key)
        print(f"DEBUG: Deleted original s3://{bucket}/{key}")

        return True
    except Exception as e:
        print(f"CRITICAL: Failed to upload or chunk document: {e}")
        return False

# NOTE: Removed the 'if __name__ == "__main__":' block to prevent Runtime.ExitError