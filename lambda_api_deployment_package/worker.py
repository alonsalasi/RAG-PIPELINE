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
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

REGION = os.getenv("AWS_REGION", "us-west-2")
BUCKET = os.getenv("S3_BUCKET", "pdfquery-rag-documents-default")
VECTOR_STORE_PATH = "vector_store/default"
EMBED_MODEL_ID = "amazon.titan-embed-text-v1"

s3 = boto3.client("s3", region_name=REGION)
textract = boto3.client("textract", region_name=REGION)
bedrock_embed = BedrockEmbeddings(model_id=EMBED_MODEL_ID, region_name=REGION)


# ==========================================================
# 🧠 Main Processing Function
# ==========================================================
def process_message(record):
    msg_id = record.get("messageId")
    logger.info(f"🟦 Processing SQS message {msg_id}")

    try:
        body = record.get("body")
        if not body:
            logger.warning("⚠️ Empty SQS body.")
            return {"messageId": msg_id, "status": "failed"}

        # Handle nested JSON from S3->SQS->SNS
        s3_event = None
        try:
            payload = json.loads(body)
            s3_event = payload.get("Records", [])[0]
        except Exception:
            try:
                nested = json.loads(json.loads(body).get("Message", "{}"))
                s3_event = nested.get("Records", [])[0]
            except Exception:
                pass

        if not s3_event:
            logger.warning(f"⚠️ No Records found after decode: {body[:200]}")
            return {"messageId": msg_id, "status": "success"}

        bucket = s3_event["s3"]["bucket"]["name"]
        key = s3_event["s3"]["object"]["key"]
        logger.info(f"📥 Processing file: s3://{bucket}/{key}")

        tmp_dir = tempfile.mkdtemp()
        local_path = os.path.join(tmp_dir, os.path.basename(key))
        s3.download_file(bucket, key, local_path)

        # Extract text (PDF or image)
        text = extract_text(local_path)
        if not text.strip():
            logger.warning("⚠️ No text extracted via OCR. Skipping Textract for PDFs.")
            # Only call Textract for images (PDF not supported by DetectDocumentText)
            if not local_path.lower().endswith(".pdf"):
                logger.info("🔄 Trying Textract fallback on image file...")
                text = extract_textract_text(local_path)
            else:
                logger.warning("🚫 Skipping Textract fallback: unsupported for PDF format.")

        if not text.strip():
            logger.warning("❌ Still no text after OCR/Textract. Skipping indexing.")
            return {"messageId": msg_id, "status": "success"}

        # Split text & build embeddings
        chunks = split_text(text)
        logger.info(f"🧩 Split text into {len(chunks)} chunks for embedding.")
        embeddings = bedrock_embed.embed_documents(chunks)
        index = FAISS.from_embeddings(list(zip(chunks, embeddings)), bedrock_embed)

        # Save to S3
        save_faiss(index)
        logger.info(f"✅ Processed and updated FAISS index for {key}")
        return {"messageId": msg_id, "status": "success"}

    except Exception as e:
        logger.error(f"🚨 LAMBDA EXECUTION FAILED: {e}")
        traceback.print_exc()
        return {"messageId": msg_id, "status": "failed"}


# ==========================================================
# 🧾 Text Extraction
# ==========================================================
def extract_text(path):
    """Perform OCR using Tesseract for Hebrew, Turkish, and English."""
    text = ""
    try:
        if path.lower().endswith(".pdf"):
            logger.info("📄 Running pdf2image OCR flow...")
            pages = convert_from_path(path)
            for i, img in enumerate(pages):
                txt = pytesseract.image_to_string(img, lang="eng+tur+heb")
                logger.info(f"🧾 OCR processed page {i + 1}/{len(pages)}")
                text += f"\n\n--- PAGE {i+1} ---\n{txt}"
        else:
            logger.info("🖼️ Running direct image OCR flow...")
            txt = pytesseract.image_to_string(path, lang="eng+tur+heb")
            text += txt
    except Exception as e:
        logger.error(f"OCR extraction error: {e}")
        traceback.print_exc()
    return text


def extract_textract_text(local_path):
    """Textract fallback for scanned image formats (PNG, JPG, TIFF)."""
    text = ""
    try:
        with open(local_path, "rb") as f:
            data = f.read()
        resp = textract.detect_document_text(Document={"Bytes": data})
        for block in resp.get("Blocks", []):
            if block["BlockType"] == "LINE":
                text += block["Text"] + "\n"
        logger.info("✅ Textract fallback extracted text successfully.")
    except ClientError as e:
        logger.error(f"Textract client error: {e}")
    except Exception as e:
        logger.error(f"Textract fallback failed: {e}")
        traceback.print_exc()
    return text


# ==========================================================
# 🪶 Text Splitting and FAISS Saving
# ==========================================================
def split_text(text):
    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=150)
    return splitter.split_text(text)


def save_faiss(store):
    """Merge into or replace FAISS on S3."""
    tmp_dir = tempfile.mkdtemp()
    faiss_file = os.path.join(tmp_dir, "index.faiss")
    pkl_file = os.path.join(tmp_dir, "index.pkl")

    store.save_local(tmp_dir)
    logger.info("💾 Saving FAISS index locally before upload...")

    s3.upload_file(faiss_file, BUCKET, f"{VECTOR_STORE_PATH}/index.faiss")
    s3.upload_file(pkl_file, BUCKET, f"{VECTOR_STORE_PATH}/index.pkl")
    logger.info(f"🆙 Uploaded FAISS index to s3://{BUCKET}/{VECTOR_STORE_PATH}/")
