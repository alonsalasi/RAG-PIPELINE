import json
import os
import uuid
import traceback
import tempfile
import boto3
from botocore.exceptions import ClientError
from langchain_community.vectorstores import FAISS
from langchain_aws import BedrockEmbeddings, ChatBedrock

# ==========================================================
# 🔧 Global Setup
# ==========================================================
session = boto3.session.Session()
REGION = session.region_name or "us-west-2"

s3_client = boto3.client("s3", region_name=REGION)
translate_client = boto3.client("translate", region_name=REGION)

BUCKET_NAME = os.getenv("S3_BUCKET", "pdfquery-rag-documents-default")
VECTOR_STORE_PATH = "vector_store/default"
EMBED_MODEL_ID = "amazon.titan-embed-text-v1"
LLM_MODEL_ID = "meta.llama3-8b-instruct-v1:0"

VECTOR_STORE = None


# ==========================================================
# 🔧 Helper Utilities
# ==========================================================
def cors_resp(status: int, body: dict):
    """Return JSON response with CORS headers."""
    return {
        "statusCode": status,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "OPTIONS,GET,POST,DELETE,PUT",
            "Access-Control-Allow-Headers": "Content-Type",
        },
        "body": json.dumps(body),
    }


def ensure_vector_store():
    """Loads FAISS index from S3 if exists, else initializes empty."""
    global VECTOR_STORE
    if VECTOR_STORE:
        return VECTOR_STORE

    tmp_dir = os.path.join(tempfile.gettempdir(), "faiss_index")
    os.makedirs(tmp_dir, exist_ok=True)
    faiss_index = os.path.join(tmp_dir, "index.faiss")
    faiss_pickle = os.path.join(tmp_dir, "index.pkl")

    exists = (
        _s3_download(f"{VECTOR_STORE_PATH}/index.faiss", faiss_index)
        and _s3_download(f"{VECTOR_STORE_PATH}/index.pkl", faiss_pickle)
    )

    embedding = BedrockEmbeddings(model_id=EMBED_MODEL_ID, region_name=REGION)
    if exists:
        VECTOR_STORE = FAISS.load_local(tmp_dir, embedding, allow_dangerous_deserialization=True)
        print("✅ Loaded FAISS vector store from S3.")
    else:
        print("⚠️ No FAISS index found. Initializing empty store.")
        VECTOR_STORE = FAISS.from_texts(["Empty"], embedding)
    return VECTOR_STORE


def _s3_download(key: str, local_path: str) -> bool:
    try:
        s3_client.download_file(BUCKET_NAME, key, local_path)
        print(f"Downloaded s3://{BUCKET_NAME}/{key}")
        return True
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey"):
            print(f"Missing on S3: s3://{BUCKET_NAME}/{key}")
            return False
        raise


def _s3_delete(key: str) -> bool:
    try:
        s3_client.delete_object(Bucket=BUCKET_NAME, Key=key)
        print(f"Deleted s3://{BUCKET_NAME}/{key}")
        return True
    except Exception as e:
        print(f"Delete error for {key}: {e}")
        return False


def _detect_lang(text: str) -> str:
    heb = sum(1 for c in text if "\u0590" <= c <= "\u05FF")
    return "he" if heb > len(text) * 0.2 else "en"


def _translate(text: str, src: str, tgt: str) -> str:
    if not text.strip():
        return text
    try:
        resp = translate_client.translate_text(Text=text, SourceLanguageCode=src, TargetLanguageCode=tgt)
        return resp["TranslatedText"]
    except Exception as e:
        print(f"Translate error {src}->{tgt}: {e}")
        return text


# ==========================================================
# 🌐 API Handlers
# ==========================================================
def handle_get_upload_url(event):
    """Generate presigned S3 PUT URL for file upload."""
    try:
        params = event.get("queryStringParameters") or {}
        # Support both 'fileName' and 'filename'
        file_name = params.get("fileName") or params.get("filename") or str(uuid.uuid4())
        key = f"uploads/{file_name}"

        # Create presigned URL for PDF upload
        url = s3_client.generate_presigned_url(
            "put_object",
            Params={"Bucket": BUCKET_NAME, "Key": key, "ContentType": "application/pdf"},
            ExpiresIn=3600,
        )

        # ✅ FIX: frontend expects 'signedUrl'
        return cors_resp(200, {"signedUrl": url, "s3Key": key})

    except Exception as e:
        print("❌ Error in handle_get_upload_url:", e)
        traceback.print_exc()
        return cors_resp(500, {"error": str(e)})


def handle_list_files(event):
    """List uploaded files in S3 uploads/ prefix."""
    try:
        resp = s3_client.list_objects_v2(Bucket=BUCKET_NAME, Prefix="uploads/")
        files = [
            {"key": obj["Key"], "size": obj["Size"], "lastModified": obj["LastModified"].isoformat()}
            for obj in resp.get("Contents", [])
            if not obj["Key"].endswith("/")
        ]
        return cors_resp(200, {"files": files})
    except Exception as e:
        print("❌ Error in handle_list_files:", e)
        traceback.print_exc()
        return cors_resp(500, {"error": str(e)})


def handle_delete_file(event):
    """Delete a specific uploaded file from S3."""
    try:
        params = json.loads(event.get("body") or "{}")
        key = params.get("key") or params.get("fileName")
        if not key:
            return cors_resp(400, {"error": "Missing 'key' parameter"})
        deleted = _s3_delete(key)
        return cors_resp(200, {"deleted": deleted})
    except Exception as e:
        print("❌ Error in handle_delete_file:", e)
        traceback.print_exc()
        return cors_resp(500, {"error": str(e)})


def handle_query(event):
    """Handle RAG-style document query."""
    try:
        payload = json.loads(event.get("body") or "{}")
        query = payload.get("query", "").strip()
        if not query:
            return cors_resp(400, {"error": "Missing query"})

        vs = ensure_vector_store()
        retriever = vs.as_retriever(search_kwargs={"k": 4})
        docs = retriever.get_relevant_documents(query)

        combined = "\n\n".join([d.page_content for d in docs])
        llm = ChatBedrock(model_id=LLM_MODEL_ID, region_name=REGION)

        prompt = f"Answer this query based on the following documents:\n{combined}\n\nQuestion: {query}"
        response = llm.invoke(prompt)

        result_text = getattr(response, "content", str(response))
        return cors_resp(200, {"response": result_text, "context": combined})

    except Exception as e:
        print("❌ Error in handle_query:", e)
        traceback.print_exc()
        return cors_resp(500, {"error": str(e)})


# ==========================================================
# Lambda Entrypoint
# ==========================================================
def lambda_handler(event, context):
    try:
        print("🚀 Lambda triggered.")
        print("DEBUG raw event:", json.dumps(event)[:1000])

        method = event.get("httpMethod", "")
        raw_path = event.get("path", "")
        path = "/" + "/".join([p for p in raw_path.split("/") if p and p != "default"])
        print("DEBUG normalized path:", path, "method:", method)

        if method == "OPTIONS":
            return cors_resp(200, {"message": "CORS preflight OK"})

        if path.endswith("/get-upload-url") and method == "GET":
            return handle_get_upload_url(event)
        if path.endswith("/list-files") and method == "GET":
            return handle_list_files(event)
        if path.endswith("/delete-file") and method == "DELETE":
            return handle_delete_file(event)
        if path.endswith("/query") and method == "POST":
            return handle_query(event)

        return cors_resp(404, {"error": f"Path not found: {path} ({method})"})

    except Exception as e:
        print("❌ Top-level Lambda error:", e)
        traceback.print_exc()
        return cors_resp(500, {"error": str(e)})
