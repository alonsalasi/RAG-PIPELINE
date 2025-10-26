import json
import os
import uuid
import traceback
import tempfile
import re
import boto3
from botocore.exceptions import ClientError
from langchain_community.vectorstores import FAISS
from langchain_aws import BedrockEmbeddings, ChatBedrock

# ------------------------------
# Env & clients
# ------------------------------
session = boto3.session.Session()
REGION = session.region_name or "us-west-2"

s3_client = boto3.client("s3", region_name=REGION)
translate_client = boto3.client("translate", region_name=REGION)

BUCKET_NAME = os.getenv("S3_BUCKET", "pdfquery-rag-documents-default")
VECTOR_STORE_PATH = "vector_store/default"
EMBED_MODEL_ID = "amazon.titan-embed-text-v1"
LLM_MODEL_ID = "meta.llama3-8b-instruct-v1:0"

VECTOR_STORE = None  # cache

# ------------------------------
# Helpers
# ------------------------------
def cors_resp(status: int, body: dict):
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
    """Lazy-load FAISS from S3 if /query is used."""
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


# ------------------------------
# Lambda handler (API Gateway)
# ------------------------------
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
        print("❌ ERROR:", e)
        traceback.print_exc()
        return cors_resp(500, {"error": str(e)})


# ------------------------------
# Route: GET /get-upload-url
# ------------------------------
def handle_get_upload_url(event):
    params = event.get("queryStringParameters") or {}
    fname = params.get("fileName", "unknown.file")
    ftype = params.get("fileType", "application/octet-stream")

    s3_key = f"uploads/{uuid.uuid4()}_{fname}"
    print(f"🪣 Generating presigned URL for s3://{BUCKET_NAME}/{s3_key}")

    try:
        url = s3_client.generate_presigned_url(
            "put_object",
            Params={"Bucket": BUCKET_NAME, "Key": s3_key, "ContentType": ftype},
            ExpiresIn=3600,
        )
        return cors_resp(200, {"signedUrl": url, "s3Key": s3_key})
    except Exception as e:
        traceback.print_exc()
        return cors_resp(500, {"error": f"Upload URL generation failed: {str(e)}"})


# ------------------------------
# Route: GET /list-files
# ------------------------------
def handle_list_files(event):
    prefix = "uploads/"
    files = []
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix=prefix):
        for obj in page.get("Contents", []) or []:
            name = obj["Key"].split("/")[-1]
            if name:
                files.append(name)
    return cors_resp(200, {"filenames": files})


# ------------------------------
# Route: DELETE /delete-file
# ------------------------------
def handle_delete_file(event):
    params = event.get("queryStringParameters") or {}
    name = params.get("fileName", "")
    if not name:
        return cors_resp(400, {"error": "Missing fileName"})

    prefix = "uploads/"
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix=prefix):
        for obj in page.get("Contents", []) or []:
            if obj["Key"].endswith(name):
                _s3_delete(obj["Key"])
                return cors_resp(200, {"message": f"Deleted {name}"})
    return cors_resp(404, {"error": "File not found"})


# ------------------------------
# Route: POST /query (enhanced with cross-doc support)
# ------------------------------
def handle_query(event):
    try:
        body = json.loads(event.get("body") or "{}")
    except Exception:
        return cors_resp(400, {"error": "Invalid JSON body"})

    q = body.get("query", "").strip()
    if not q:
        return cors_resp(400, {"error": "Missing query"})

    vs = ensure_vector_store()

    # --- Get top 12 docs across all
    raw_docs = vs.similarity_search(q, k=12)
    if not raw_docs:
        return cors_resp(200, {"response": "I don't know.", "source_documents": []})

    # --- Group by source
    grouped = {}
    for d in raw_docs:
        src = d.metadata.get("source_key", "unknown")
        grouped.setdefault(src, []).append(d)

    # --- Detect if it's a comparison query (contains multiple brands)
    compare_targets = re.findall(r"\b(Chery|Cherry|Hyundai|Toyota|Kia|Mazda)\b", q, re.IGNORECASE)
    compare_targets = list(set([c.lower() for c in compare_targets]))
    print("Detected compare targets:", compare_targets)

    src_lang = _detect_lang(q)
    translated_q = _translate(q, "he", "en") if src_lang == "he" else q
    llm = ChatBedrock(model_id=LLM_MODEL_ID, region_name=REGION)

    # --- If comparing multiple brands (cross-doc)
    if len(compare_targets) >= 2 and len(grouped) > 1:
        summaries = []
        for src, docs in grouped.items():
            ctx = "\n\n".join(d.page_content.strip() for d in docs if len(d.page_content.strip()) > 30)[:6000]
            brand_name = os.path.basename(src).split("_")[-1].split(".")[0]
            sub_prompt = f"""
Summarize the key details about {brand_name} from the following context, focusing on engine, color, specs, and notable features.

Context:
{ctx}
"""
            try:
                resp = llm.invoke(sub_prompt)
                summaries.append(f"{brand_name}:\n{resp.content.strip()}")
            except Exception as e:
                summaries.append(f"{brand_name}: (summary unavailable: {e})")

        comparison_prompt = f"""
Compare the following vehicle summaries and highlight key differences and similarities.
Question: {translated_q}

Summaries:
{chr(10).join(summaries)}

Answer:
"""
        try:
            resp = llm.invoke(comparison_prompt)
            ans = resp.content.strip()
        except Exception as e:
            ans = f"I couldn't compare the documents due to an error: {e}"

        final = _translate(ans, "en", "he") if src_lang == "he" else ans
        return cors_resp(200, {"question": q, "response": final, "source_documents": list(grouped.keys())})

    # --- Single-brand or normal question
    best_src = None
    for src in grouped:
        if any(word in src.lower() for word in q.lower().split()):
            best_src = src
            break
    if not best_src:
        best_src = max(grouped.keys(), key=lambda s: len(grouped[s]))

    docs = grouped[best_src]
    context = "\n\n".join(d.page_content.strip() for d in docs if len(d.page_content.strip()) > 30)[:8000]
    prompt = f"""
You are a multilingual assistant answering ONLY from the context below.
If uncertain, say "I don't know."
Answer in the same language as the question.

Context (from {best_src}):
{context}

Question:
{translated_q}

Answer:
"""
    try:
        response = llm.invoke(prompt)
        ans = response.content.strip() or "I don't know."
    except Exception as e:
        print("LLM error:", e)
        ans = "I don't know."

    final = _translate(ans, "en", "he") if src_lang == "he" else ans
    return cors_resp(200, {"question": q, "response": final, "source_documents": [best_src]})
