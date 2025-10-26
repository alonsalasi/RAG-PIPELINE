import os
import json
import tempfile
import traceback
import boto3
from botocore.exceptions import ClientError
from pdf2image import convert_from_path
import pytesseract
from langchain_community.vectorstores import FAISS
from langchain_aws import BedrockEmbeddings
from langchain_community.document_loaders import PyPDFLoader

# --------------------------------------------------
# Global Clients and Configuration
# --------------------------------------------------
s3_client = boto3.client("s3")
translate_client = boto3.client("translate")

BUCKET_NAME = os.getenv("S3_BUCKET", "pdfquery-rag-documents-default")
VECTOR_STORE_PATH = "vector_store/default"
EMBED_MODEL_ID = "amazon.titan-embed-text-v1"
REGION = os.getenv("AWS_REGION", "us-west-2")

# --------------------------------------------------
# Helper Functions
# --------------------------------------------------
def download_from_s3(bucket, key, local_path):
    try:
        s3_client.download_file(bucket, key, local_path)
        print(f"✅ Downloaded: s3://{bucket}/{key}")
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey"):
            print(f"⚠️ File not found on S3: {key}")
            return False
        raise


def upload_to_s3(bucket, key, local_path):
    s3_client.upload_file(local_path, bucket, key)
    print(f"⬆️ Uploaded: s3://{bucket}/{key}")


def detect_language(text):
    heb_chars = sum(1 for c in text if "\u0590" <= c <= "\u05FF")
    return "he" if heb_chars > len(text) * 0.2 else "en"


def translate_text(text, src="he", tgt="en"):
    if not text.strip():
        return text
    try:
        resp = translate_client.translate_text(Text=text, SourceLanguageCode=src, TargetLanguageCode=tgt)
        return resp["TranslatedText"]
    except Exception as e:
        print(f"⚠️ Translate failed: {e}")
        return text


def extract_text_from_pdf(pdf_path):
    """Try PyPDF first, then OCR fallback"""
    try:
        loader = PyPDFLoader(pdf_path)
        docs = loader.load()
        print(f"✅ Extracted {len(docs)} pages with PyPDFLoader.")
        return "\n".join([d.page_content for d in docs])
    except Exception as e:
        print(f"❌ PyPDFLoader failed: {e}. Falling back to OCR.")
        return extract_text_with_ocr(pdf_path)


def extract_text_with_ocr(pdf_path):
    text = ""
    try:
        images = convert_from_path(pdf_path)
        print(f"OCR processing {len(images)} pages...")
        for i, img in enumerate(images, start=1):
            print(f"OCR page {i}/{len(images)} ...")
            text += pytesseract.image_to_string(img, lang="eng+heb")
        return text
    except Exception as e:
        print(f"⚠️ OCR failed: {e}")
        return ""


def split_text_into_chunks(text, max_chunk_size=2000):
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks, current = [], ""
    for para in paragraphs:
        if len(current) + len(para) < max_chunk_size:
            current += " " + para
        else:
            chunks.append(current.strip())
            current = para
    if current:
        chunks.append(current.strip())
    print(f"✅ Split into {len(chunks)} chunks.")
    return chunks


def load_faiss_index(tmp_dir, embedding_model):
    """Load FAISS index from S3 if exists"""
    faiss_index = os.path.join(tmp_dir, "index.faiss")
    faiss_pkl = os.path.join(tmp_dir, "index.pkl")

    exists = (
        download_from_s3(BUCKET_NAME, f"{VECTOR_STORE_PATH}/index.faiss", faiss_index)
        and download_from_s3(BUCKET_NAME, f"{VECTOR_STORE_PATH}/index.pkl", faiss_pkl)
    )
    if not exists:
        print("⚠️ No FAISS index found.")
        return None, False

    try:
        store = FAISS.load_local(tmp_dir, embedding_model, allow_dangerous_deserialization=True)
        print("✅ Loaded existing FAISS index from S3.")
        return store, True
    except Exception as e:
        print(f"⚠️ Failed to load FAISS: {e}")
        return None, False


# --------------------------------------------------
# Main Processing Logic
# --------------------------------------------------
def process_message(event):
    print("🚀 Worker triggered with event:", json.dumps(event)[:800])

    try:
        record = event["Records"][0]
        s3_info = record["s3"]
        bucket = s3_info["bucket"]["name"]
        s3_key = s3_info["object"]["key"]
    except Exception as e:
        print(f"❌ Invalid S3 event: {e}")
        return False

    print(f"📦 Processing S3 object: s3://{bucket}/{s3_key}")

    with tempfile.TemporaryDirectory() as tmpdir:
        local_pdf = os.path.join(tmpdir, os.path.basename(s3_key))
        s3_client.download_file(bucket, s3_key, local_pdf)
        print(f"✅ Downloaded {s3_key} from S3.")

        text = extract_text_from_pdf(local_pdf)
        if not text.strip():
            print("❌ No text extracted from PDF.")
            return False

        lang = detect_language(text)
        if lang == "he":
            text = translate_text(text, "he", "en")

        chunks = split_text_into_chunks(text)

        embedding_model = BedrockEmbeddings(model_id=EMBED_MODEL_ID, region_name=REGION)

        faiss_dir = os.path.join(tmpdir, "faiss_store")
        os.makedirs(faiss_dir, exist_ok=True)

        existing_faiss, existing = load_faiss_index(faiss_dir, embedding_model)

        # New document embeddings
        new_docs = [chunk for chunk in chunks if chunk.strip()]
        new_metadatas = [{"source_key": os.path.basename(s3_key)} for _ in new_docs]
        new_store = FAISS.from_texts(new_docs, embedding_model, metadatas=new_metadatas)

        if existing and existing_faiss:
            print("🔁 Merging new vectors into existing FAISS index...")
            existing_faiss.merge_from(new_store)
            final_store = existing_faiss
        else:
            print("🆕 Creating new FAISS index...")
            final_store = new_store

        final_store.save_local(faiss_dir)
        upload_to_s3(bucket, f"{VECTOR_STORE_PATH}/index.faiss", os.path.join(faiss_dir, "index.faiss"))
        upload_to_s3(bucket, f"{VECTOR_STORE_PATH}/index.pkl", os.path.join(faiss_dir, "index.pkl"))

        print(f"✅ Vector store updated with {len(new_docs)} new chunks from {os.path.basename(s3_key)}")

    return True


# --------------------------------------------------
# Lambda Entrypoint
# --------------------------------------------------
def lambda_handler(event, context):
    try:
        print("🚀 Ingestion Lambda triggered.")
        print("DEBUG raw event:", json.dumps(event)[:800])

        for record in event.get("Records", []):
            print(f"🟦 Processing SQS message {record.get('messageId', 'unknown')}")
            body = json.loads(record.get("body", "{}"))
            s3_event = body.get("Records", [])[0] if "Records" in body else None

            if not s3_event:
                print(f"⚠️ Missing s3_key in message body.")
                continue

            success = process_message({"Records": [s3_event]})
            if success:
                print(f"✅ Message {record.get('messageId')} processed successfully.")
            else:
                print(f"❌ Message {record.get('messageId')} failed.")

        print("🎉 All records processed.")
        return {"statusCode": 200, "body": json.dumps({"message": "Processing complete"})}

    except Exception as e:
        print(f"🚨 LAMBDA EXECUTION FAILED: {e}")
        traceback.print_exc()
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
