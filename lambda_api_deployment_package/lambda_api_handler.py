# ==========================================================
# AUTO-INSTALL REQUIRED LIBRARIES (NO LAYERS NEEDED)
# ==========================================================
import subprocess
import sys
import importlib

REQUIRED_LIBS = [
    "faiss-cpu",
    "langchain==0.2.14",
    "langchain-aws==0.1.8",
    "numpy>=1.26.0"
]

for lib in REQUIRED_LIBS:
    lib_name = lib.split("==")[0].split(">=")[0].replace("-", "_")
    try:
        importlib.import_module(lib_name)
    except ImportError:
        print(f"Installing missing library: {lib}")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", lib, "-t", "/tmp"],
            check=True,
        )
        sys.path.append("/tmp")

# ==========================================================
# STANDARD IMPORTS
# ==========================================================
import os
import json
import time
import boto3
import re
import shutil
from collections import defaultdict
from botocore.exceptions import ClientError

# ==========================================================
# LANGCHAIN IMPORTS
# ==========================================================
from langchain_core.documents import Document
from langchain_aws import BedrockLLM, BedrockEmbeddings
from langchain.vectorstores import FAISS

# ==========================================================
# CONFIGURATION
# ==========================================================
S3_DOCUMENTS_BUCKET = os.environ.get("S3_DOCUMENTS_BUCKET")
AWS_REGION = os.environ.get("AWS_REGION", "us-west-2")

BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "meta.llama3-8b-instruct-v1:0")
BEDROCK_EMBEDDINGS_ID = os.environ.get("BEDROCK_EMBEDDINGS_ID", "amazon.titan-embed-text-v2")

VECTOR_STORE_S3_PREFIX = os.environ.get("VECTOR_STORE_S3_PREFIX", "vector_store/default")
LOCAL_FAISS_DIR = "/tmp/faiss_index"

MAX_CONTEXT_CHUNKS = 5

# ==========================================================
# AWS CLIENTS
# ==========================================================
s3_client = boto3.client("s3", region_name=AWS_REGION)
bedrock_client = boto3.client("bedrock-runtime", region_name=AWS_REGION)

llm = BedrockLLM(client=bedrock_client, model_id=BEDROCK_MODEL_ID)
embedding_model = BedrockEmbeddings(model_id=BEDROCK_EMBEDDINGS_ID, client=bedrock_client)

DOCUMENT_CACHE = {}
VECTOR_STORE = None
LAST_UPDATE_TIME = 0

# ==========================================================
# FAISS UTILITIES (S3 SYNC)
# ==========================================================
def _clear_local_faiss_dir():
    try:
        if os.path.isdir(LOCAL_FAISS_DIR):
            shutil.rmtree(LOCAL_FAISS_DIR)
        os.makedirs(LOCAL_FAISS_DIR, exist_ok=True)
    except Exception as e:
        print(f"WARNING: Could not clear local FAISS dir: {e}")

def _s3_key(prefix, filename):
    if not prefix.endswith("/"):
        prefix += "/"
    return f"{prefix}{filename}"

def download_faiss_from_s3():
    """Download FAISS artifacts (index.faiss + index.pkl) from S3."""
    _clear_local_faiss_dir()
    needed = ["index.faiss", "index.pkl"]
    ok = True
    for fname in needed:
        key = _s3_key(VECTOR_STORE_S3_PREFIX, fname)
        try:
            print(f"Downloading s3://{S3_DOCUMENTS_BUCKET}/{key}")
            s3_client.download_file(S3_DOCUMENTS_BUCKET, key, os.path.join(LOCAL_FAISS_DIR, fname))
        except Exception as e:
            print(f"FAISS artifact missing on S3: {key} ({e})")
            ok = False
    return ok and all(os.path.isfile(os.path.join(LOCAL_FAISS_DIR, f)) for f in needed)

def upload_faiss_to_s3():
    """Upload FAISS index files to S3."""
    for fname in ["index.faiss", "index.pkl"]:
        local_path = os.path.join(LOCAL_FAISS_DIR, fname)
        if not os.path.isfile(local_path):
            continue
        key = _s3_key(VECTOR_STORE_S3_PREFIX, fname)
        print(f"Uploading {local_path} -> s3://{S3_DOCUMENTS_BUCKET}/{key}")
        s3_client.upload_file(local_path, S3_DOCUMENTS_BUCKET, key)

# ==========================================================
# DOCUMENT MANAGEMENT
# ==========================================================
def load_documents_from_s3():
    """Load processed chunks from S3."""
    global DOCUMENT_CACHE, LAST_UPDATE_TIME
    print("Reloading document cache from S3...")
    new_cache = defaultdict(list)

    resp = s3_client.list_objects_v2(Bucket=S3_DOCUMENTS_BUCKET, Prefix="processed_chunks/")
    contents = resp.get("Contents", [])
    if not contents:
        DOCUMENT_CACHE = {}
        print("No processed chunk files found.")
        return

    for item in contents:
        key = item.get("Key")
        if not key.endswith(".json"):
            continue
        try:
            obj = s3_client.get_object(Bucket=S3_DOCUMENTS_BUCKET, Key=key)
            data = json.loads(obj["Body"].read().decode("utf-8"))
            for chunk in data:
                md = chunk.get("metadata", {})
                src = md.get("source_key")
                if src:
                    new_cache[src].append(
                        Document(page_content=chunk["page_content"], metadata=md)
                    )
        except Exception as e:
            print(f"Error loading {key}: {e}")

    DOCUMENT_CACHE = new_cache
    LAST_UPDATE_TIME = time.time()
    print(f"Loaded {sum(len(v) for v in DOCUMENT_CACHE.values())} chunks.")

def build_vector_store_from_cache():
    """Build FAISS from document cache and upload."""
    global VECTOR_STORE
    print("Building FAISS index...")
    all_docs = [doc for docs in DOCUMENT_CACHE.values() for doc in docs]
    if not all_docs:
        print("No documents to index.")
        return

    VECTOR_STORE = FAISS.from_documents(all_docs, embedding_model)
    _clear_local_faiss_dir()
    VECTOR_STORE.save_local(LOCAL_FAISS_DIR)
    upload_faiss_to_s3()
    print(f"FAISS index built with {len(all_docs)} docs and uploaded.")

def ensure_vector_store():
    """Load FAISS from S3 or rebuild if missing."""
    global VECTOR_STORE
    if VECTOR_STORE:
        return
    try:
        if download_faiss_from_s3():
            VECTOR_STORE = FAISS.load_local(LOCAL_FAISS_DIR, embeddings=embedding_model, allow_dangerous_deserialization=True)
            print("Loaded FAISS from S3 successfully.")
            return
    except Exception as e:
        print(f"Failed to load FAISS: {e}")
    if not DOCUMENT_CACHE:
        load_documents_from_s3()
    build_vector_store_from_cache()

# ==========================================================
# RETRIEVAL + LLM
# ==========================================================
def semantic_retriever(query, k=MAX_CONTEXT_CHUNKS):
    if not VECTOR_STORE:
        ensure_vector_store()
    if not VECTOR_STORE:
        print("No vector store available.")
        return []
    return VECTOR_STORE.similarity_search(query, k=k)

def detect_language(text):
    """Detect if text is Hebrew or English."""
    hebrew_chars = re.findall(r'[\u0590-\u05FF]', text)
    english_chars = re.findall(r'[A-Za-z]', text)
    return "hebrew" if len(hebrew_chars) > len(english_chars) else "english"

def invoke_rag_chain(query, retrieved_context):
    """Generate a bilingual RAG answer."""
    context_text = "\n\n".join(d.page_content for d in retrieved_context)
    sources = [d.metadata.get("source_key") for d in retrieved_context if d.metadata.get("source_key")]

    lang = detect_language(query)
    lang_instruction = "Answer fully in Hebrew only." if lang == "hebrew" else "Answer fully in English only."

    prompt = f"""
You are a retrieval-augmented assistant that answers questions strictly using the provided context.
{lang_instruction}
If the answer is not found in the context, respond only with: "I don't know."
Do not restate or translate the question. Keep answers concise and factual.

CONTEXT:
{context_text}

QUESTION:
{query}
"""
    response = llm.invoke(prompt)
    return {"response": response.strip(), "source_documents": sources}

# ==========================================================
# FILE OPS
# ==========================================================
def get_presigned_url(file_name, file_type):
    ts = int(time.time())
    key = f"incoming/{ts}_{file_name}"
    url = s3_client.generate_presigned_url(
        ClientMethod="put_object",
        Params={"Bucket": S3_DOCUMENTS_BUCKET, "Key": key, "ContentType": file_type},
        ExpiresIn=300,
    )
    return url, key

def list_available_files():
    files = set()
    if DOCUMENT_CACHE:
        for key in DOCUMENT_CACHE.keys():
            files.add(os.path.basename(key))
    if not files:
        try:
            resp = s3_client.list_objects_v2(Bucket=S3_DOCUMENTS_BUCKET, Prefix="incoming/")
            for item in resp.get("Contents", []):
                files.add(os.path.basename(item["Key"]))
        except Exception as e:
            print(f"Error listing files: {e}")
    return sorted(files)

# ==========================================================
# HANDLER
# ==========================================================
def lambda_handler(event, context):
    import worker

    CORS = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, X-Amz-Date, Authorization, X-Api-Key, X-Amz-Security-Token",
    }

    path = event.get("rawPath") or event.get("path") or ""
    method = (
        event.get("requestContext", {}).get("http", {}).get("method")
        or event.get("httpMethod")
        or "UNKNOWN"
    )
    print(f"DEBUG: Received request {method} {path}")

    if method == "OPTIONS":
        return {"statusCode": 200, "headers": CORS}

    # List files
    if "/list-files" in path and method == "GET":
        if not DOCUMENT_CACHE:
            load_documents_from_s3()
        return {
            "statusCode": 200,
            "headers": CORS,
            "body": json.dumps({"filenames": list_available_files()}),
        }

    # Upload URL
    if "/get-upload-url" in path and method == "GET":
        params = event.get("queryStringParameters", {}) or {}
        name = params.get("fileName")
        ftype = params.get("fileType")
        if not name or not ftype:
            return {"statusCode": 400, "headers": CORS, "body": json.dumps({"error": "Missing parameters"})}
        url, key = get_presigned_url(name, ftype)
        return {"statusCode": 200, "headers": CORS, "body": json.dumps({"signedUrl": url, "s3Key": key})}

    # Query
    if "/query" in path and method == "POST":
        if not DOCUMENT_CACHE:
            load_documents_from_s3()
        ensure_vector_store()
        body = json.loads(event.get("body") or "{}")
        query = body.get("query")
        if not query:
            return {"statusCode": 400, "headers": CORS, "body": json.dumps({"error": "Missing query"})}
        docs = semantic_retriever(query)
        if not docs:
            return {"statusCode": 200, "headers": CORS, "body": json.dumps({"response": "I don't know.", "source_documents": []})}
        result = invoke_rag_chain(query, docs)
        return {"statusCode": 200, "headers": CORS, "body": json.dumps(result)}

    # Health
    if "/health" in path and method == "GET":
        status = "ok" if DOCUMENT_CACHE else "loading"
        return {"statusCode": 200, "headers": CORS, "body": json.dumps({"status": status})}

    print(f"WARNING: Unmatched path {path}")
    return {"statusCode": 404, "headers": CORS, "body": json.dumps({"error": f"Unknown path {path}"})}
