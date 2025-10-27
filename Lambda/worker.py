import os
import json
import tempfile
import boto3
import logging
import traceback
import pytesseract
from pdf2image import convert_from_path
from langchain_community.vectorstores import FAISS
from langchain_aws import BedrockEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
import easyocr

# --- Initialize Logging ---
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# --- Environment Variables ---
REGION = os.getenv("AWS_REGION", "us-west-2")
BUCKET = os.getenv("S3_BUCKET", "pdfquery-rag-documents-default")
VECTOR_STORE_PATH = "vector_store/default"
EMBED_MODEL_ID = "amazon.titan-embed-text-v1"

# --- AWS Clients ---
s3 = boto3.client("s3", region_name=REGION)
textract = boto3.client("textract", region_name=REGION)
bedrock_embed = BedrockEmbeddings(model_id=EMBED_MODEL_ID, region_name=REGION)

# --- OCR Setup ---
pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'
easyocr_reader = easyocr.Reader(['he', 'en'], gpu=False)


# ============================================================
# 🧩 MAIN ENTRY POINT: SQS Message Processing
# ============================================================
def process_message(record):
    msg_id = record.get("messageId")
    logger.info(f"🟦 Processing SQS message {msg_id}")

    try:
        body = record.get("body")
        if not body:
            logger.warning("⚠️ Empty SQS body, skipping.")
            return

        # Decode S3 event from SQS message
        s3_event = None
        payload = None
        try:
            payload = json.loads(body)
            s3_event = payload.get("Records", [])[0]
        except Exception:
            pass

        if not s3_event:
            try:
                nested = json.loads(json.loads(body).get("Message", "{}"))
                s3_event = nested.get("Records", [])[0]
            except Exception:
                pass

        if not s3_event:
            logger.warning(f"⚠️ No valid S3 record found in event: {payload}")
            return

        bucket = s3_event["s3"]["bucket"]["name"]
        key = s3_event["s3"]["object"]["key"]
        logger.info(f"📥 Processing file: s3://{bucket}/{key}")

        # --- Download to temp ---
        tmp_dir = tempfile.mkdtemp()
        local_path = os.path.join(tmp_dir, os.path.basename(key))
        s3.download_file(bucket, key, local_path)

        # --- OCR Phase ---
        text = extract_text(local_path)

        # Log for debugging
        logger.info(f"📏 Extracted text length (Tesseract/EasyOCR): {len(text)}")

        # Fallback to Textract if no text found
        if not text.strip():
            logger.warning("⚠️ No text extracted. Trying Textract fallback.")
            text = extract_textract_text(local_path, bucket, key)
            logger.info(f"📏 Extracted text length (Textract): {len(text)}")

        if not text.strip():
            logger.warning(f"❌ Still no text after Textract for s3://{bucket}/{key}.")
            raise Exception(f"No text could be extracted from s3://{bucket}/{key}")

        # --- Debug: Save raw extracted text to S3 for inspection ---
        save_debug_text(bucket, key, text)

        # --- Split and Embed ---
        chunks = split_text(text)
        embeddings = bedrock_embed.embed_documents(chunks)
        index = FAISS.from_embeddings(list(zip(chunks, embeddings)), bedrock_embed)

        # --- Save Vector Index + Marker JSON ---
        save_faiss(index, key)
        logger.info(f"✅ Processed and updated FAISS index for {key}")

    except Exception as e:
        logger.error(f"🚨 LAMBDA EXECUTION FAILED for {msg_id}: {e}")
        traceback.print_exc()
        raise e


# ============================================================
# 🧩 OCR + TEXTRACT + EASYOCR
# ============================================================
def extract_text(path):
    """Perform OCR using Tesseract + EasyOCR for Hebrew/English."""
    text = ""
    try:
        if path.lower().endswith(".pdf"):
            pages = convert_from_path(path)
            for i, img in enumerate(pages):
                # First try Tesseract
                tesseract_txt = pytesseract.image_to_string(img, lang="eng+tur+heb").strip()
                if tesseract_txt:
                    text += f"\n\n--- PAGE {i+1} (Tesseract) ---\n{tesseract_txt}"
                else:
                    # Fallback to EasyOCR
                    logger.info(f"⚙️ Falling back to EasyOCR for page {i+1}")
                    easy_txt = easyocr_reader.readtext(img, detail=0, paragraph=True)
                    if easy_txt:
                        text += f"\n\n--- PAGE {i+1} (EasyOCR) ---\n" + "\n".join(easy_txt)
        else:
            txt = pytesseract.image_to_string(path, lang="eng+tur+heb").strip()
            if not txt:
                easy_txt = easyocr_reader.readtext(path, detail=0, paragraph=True)
                txt = "\n".join(easy_txt)
            text += txt
    except Exception as e:
        logger.error(f"OCR extraction error: {e}")
    return text


def extract_textract_text(local_path, bucket, key):
    """Textract fallback for scanned or complex PDFs."""
    text = ""
    try:
        with open(local_path, "rb") as f:
            data = f.read()
        resp = textract.detect_document_text(Document={"Bytes": data})
        for block in resp.get("Blocks", []):
            if block["BlockType"] == "LINE":
                text += block["Text"] + "\n"
        logger.info("✅ Textract fallback extracted text.")
    except Exception as e:
        logger.error(f"Textract fallback failed: {e}")
    return text


# ============================================================
# 🧩 TEXT SPLITTING + VECTOR STORAGE
# ============================================================
def split_text(text):
    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=150)
    return splitter.split_text(text)


def save_faiss(store, original_key):
    """Save FAISS index and write a processed marker JSON in /processed/."""
    tmp_dir = tempfile.mkdtemp()
    faiss_file = os.path.join(tmp_dir, "index.faiss")
    pkl_file = os.path.join(tmp_dir, "index.pkl")

    store.save_local(tmp_dir)

    s3.upload_file(faiss_file, BUCKET, f"{VECTOR_STORE_PATH}/index.faiss")
    s3.upload_file(pkl_file, BUCKET, f"{VECTOR_STORE_PATH}/index.pkl")
    logger.info("🆙 Uploaded FAISS index to S3.")

    # ✅ Write processed marker in /processed/
    base_name = os.path.splitext(os.path.basename(original_key))[0]
    marker_key = f"processed/{base_name}.json"
    marker_content = {
        "source_file": original_key,
        "status": "processed"
    }

    s3.put_object(
        Bucket=BUCKET,
        Key=marker_key,
        Body=json.dumps(marker_content),
        ContentType="application/json"
    )

    logger.info(f"✅ Marker written to s3://{BUCKET}/{marker_key}")


# ============================================================
# 🪶 DEBUG UTILITIES
# ============================================================
def save_debug_text(bucket, original_key, text):
    """Save the raw extracted text for debugging OCR output."""
    try:
        base_name = os.path.splitext(os.path.basename(original_key))[0]
        debug_key = f"processed_text/{base_name}.txt"
        s3.put_object(
            Bucket=bucket,
            Key=debug_key,
            Body=text.encode("utf-8"),
            ContentType="text/plain"
        )
        logger.info(f"🪶 Saved raw extracted text to s3://{bucket}/{debug_key}")
    except Exception as e:
        logger.error(f"Failed to save debug text: {e}")
