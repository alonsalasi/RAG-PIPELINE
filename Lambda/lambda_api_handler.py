import os
import json
import boto3
import logging
import traceback
from langchain_aws import BedrockEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.chains import RetrievalQA
from langchain.llms.bedrock import Bedrock

# Setup logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# --- Environment Variables ---
AWS_REGION = os.getenv("AWS_REGION", "us-west-2")
BUCKET_NAME = os.getenv("S3_BUCKET", "pdfquery-rag-documents-default")
VECTOR_STORE_PATH = "vector_store/default"
EMBED_MODEL_ID = "amazon.titan-embed-text-v1"
LLM_MODEL_ID = "amazon.titan-text-lite-v1"

# --- AWS Clients ---
s3 = boto3.client("s3", region_name=AWS_REGION)

# --- Helper: CORS response ---
def _response(status, body):
    return {
        "statusCode": status,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        },
        "body": json.dumps(body),
    }

# --- Entrypoint ---
def lambda_handler(event, context):
    logger.info("🚀 Lambda triggered.")
    logger.debug(f"DEBUG raw event: {json.dumps(event)[:1000]}")

    # Handle CORS preflight (OPTIONS)
    route_key = f"{event.get('httpMethod', '')} {event.get('path', '')}"
    if event.get("requestContext", {}).get("http", {}).get("method") == "OPTIONS" or "OPTIONS" in route_key:
        logger.info("✅ Handling OPTIONS preflight request.")
        return _response(200, {"message": "CORS preflight OK"})

    # Normalize route for API Gateway v1/v2
    method = (
        event.get("requestContext", {}).get("http", {}).get("method")
        or event.get("httpMethod", "")
    )
    raw_path = (
        event.get("requestContext", {}).get("http", {}).get("path")
        or event.get("path", "")
    )
    route_key = f"{method} {raw_path}"
    logger.debug(f"DEBUG normalized path: {route_key}")

    # --- Routing ---
    try:
        if "/list-files" in raw_path:
            return handle_list_files()
        elif "/get-upload-url" in raw_path:
            return handle_get_upload_url(event)
        elif "/delete-file" in raw_path:
            return handle_delete_file(event)
        elif "/query" in raw_path:
            return handle_query(event)
        else:
            logger.warning(f"Unhandled route: {route_key}")
            return _response(400, {"error": f"Unhandled route: {route_key}"})
    except Exception as e:
        logger.error(f"❌ Exception in main handler: {e}")
        traceback.print_exc()
        return _response(500, {"error": str(e)})


# =========================================================
# 🧩 LIST FILES
# =========================================================
def handle_list_files():
    logger.info("📄 Listing processed JSON markers...")
    prefixes = [
        "processed/",
        "vector_store/",
        "vector_store/default/",
        "processed_chunks/",
        "processed_chunks/default/",
    ]
    filenames = []
    try:
        for prefix in prefixes:
            resp = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=prefix)
            for obj in resp.get("Contents", []):
                if obj["Key"].endswith(".json"):
                    filenames.append(os.path.basename(obj["Key"]))
        logger.info(f"📦 Found {len(filenames)} processed JSON marker(s): {filenames}")
        return _response(200, {"filenames": filenames})
    except Exception as e:
        logger.error(f"❌ Error listing processed files: {e}")
        return _response(500, {"error": str(e)})


# =========================================================
# 🧩 GET UPLOAD URL
# =========================================================
def handle_get_upload_url(event):
    try:
        params = event.get("queryStringParameters") or {}
        file_name = params.get("fileName")
        file_type = params.get("fileType", "application/octet-stream")

        if not file_name:
            return _response(400, {"error": "Missing fileName"})

        key = f"uploads/{file_name}"
        logger.info(f"🔗 Generating presigned URL for {key}")

        signed_url = s3.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": BUCKET_NAME,
                "Key": key,
                "ContentType": file_type,
            },
            ExpiresIn=3600,
        )
        return _response(200, {"signedUrl": signed_url})
    except Exception as e:
        logger.error(f"❌ Error generating upload URL: {e}")
        return _response(500, {"error": str(e)})


# =========================================================
# 🧩 DELETE FILE — Updated version
# =========================================================
def handle_delete_file(event):
    logger.info("🗑️ Delete file handler invoked.")
    params = event.get("queryStringParameters") or {}
    display_name = params.get("fileName")
    if not display_name:
        return _response(400, {"error": "Missing fileName"})

    try:
        # Delete JSON marker
        marker_key = f"processed/{display_name}.json"
        s3.delete_object(Bucket=BUCKET_NAME, Key=marker_key)
        logger.info(f"✅ Deleted marker: {marker_key}")

        # Delete uploaded PDF (in uploads/)
        possible_pdf = f"uploads/{display_name.replace('.json', '.pdf')}"
        try:
            s3.delete_object(Bucket=BUCKET_NAME, Key=possible_pdf)
            logger.info(f"✅ Deleted PDF: {possible_pdf}")
        except Exception:
            logger.warning(f"⚠️ Could not delete PDF for {display_name}")

        return _response(200, {"message": f"{display_name} and related file(s) deleted."})

    except Exception as e:
        logger.error(f"❌ Error deleting file: {e}")
        traceback.print_exc()
        return _response(500, {"error": str(e)})


# =========================================================
# 🧩 QUERY HANDLER — Real Bedrock + FAISS logic
# =========================================================
def handle_query(event):
    logger.info("🧠 Handling /query request")

    # Handle both payload formats (API GW v1/v2)
    body = event.get("body")
    if body is None:
        logger.warning("⚠️ event['body'] is None — checking for v2.0 format.")
        return _response(400, {"error": "No body in request"})

    try:
        data = json.loads(body)
        query = data.get("query", "").strip()
        if not query:
            return _response(400, {"error": "Missing 'query' field"})
    except Exception as e:
        logger.error(f"❌ Failed to parse JSON body: {e}")
        return _response(400, {"error": "Invalid JSON body"})

    try:
        # --- Load FAISS index from S3 ---
        logger.info("📦 Loading FAISS index from S3...")
        tmp_dir = "/tmp/vector_store"
        os.makedirs(tmp_dir, exist_ok=True)
        s3.download_file(BUCKET_NAME, f"{VECTOR_STORE_PATH}/index.faiss", f"{tmp_dir}/index.faiss")
        s3.download_file(BUCKET_NAME, f"{VECTOR_STORE_PATH}/index.pkl", f"{tmp_dir}/index.pkl")

        embeddings = BedrockEmbeddings(model_id=EMBED_MODEL_ID, region_name=AWS_REGION)
        vectorstore = FAISS.load_local(tmp_dir, embeddings, allow_dangerous_deserialization=True)

        # --- Run RetrievalQA ---
        retriever = vectorstore.as_retriever(search_kwargs={"k": 4})
        llm = Bedrock(model_id=LLM_MODEL_ID, region_name=AWS_REGION)

        qa = RetrievalQA.from_chain_type(
            llm=llm,
            retriever=retriever,
            chain_type="stuff",
        )

        logger.info(f"💬 Query: {query}")
        answer = qa.run(query)
        sources = [doc.metadata.get("source", "unknown") for doc in retriever.get_relevant_documents(query)]

        logger.info("✅ Query processed successfully.")
        return _response(200, {"response": answer, "source_documents": sources})

    except Exception as e:
        logger.error(f"❌ Query error: {e}")
        traceback.print_exc()
        return _response(500, {"error": str(e)})
