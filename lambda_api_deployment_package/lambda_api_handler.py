import json
import os
import sys
import boto3
import time
import re
from collections import defaultdict
from botocore.exceptions import ClientError

# Ensure local imports work
sys.path.insert(0, os.path.dirname(__file__))

# --- RAG / LLM Imports ---
import worker
from langchain.chains import RetrievalQA
from langchain_aws import ChatBedrock
from langchain_core.documents import Document

# --- Configuration (from Lambda Environment Variables) ---
S3_DOCUMENTS_BUCKET = os.environ.get("S3_DOCUMENTS_BUCKET")
AWS_REGION = os.environ.get("AWS_REGION", "us-west-2")

# --- Constants ---
PRIMARY_MODEL_ID = "anthropic.claude-3-sonnet-20240229-v1:0"
FALLBACK_MODEL_ID = "amazon.titan-text-lite-v1"
MAX_CONTEXT_CHUNKS = 5

# Initialize Boto3 clients
s3_client = boto3.client("s3", region_name=AWS_REGION)
bedrock_client = boto3.client("bedrock-runtime", region_name=AWS_REGION)

# Initialize the default LLM
def create_llm(model_id: str):
    """Helper to create a ChatBedrock instance for the given model."""
    provider = "anthropic" if "anthropic" in model_id else "amazon"
    return ChatBedrock(client=bedrock_client, model_id=model_id, provider=provider)

llm = create_llm(PRIMARY_MODEL_ID)

# Global cache for document content
DOCUMENT_CACHE = {}
LAST_UPDATE_TIME = 0


# ---------------------------------------------------------------------------
# DOCUMENT MANAGEMENT
# ---------------------------------------------------------------------------

def load_documents_from_s3():
    """Loads all chunked documents (JSON files) saved by the ingestion worker into memory."""
    global DOCUMENT_CACHE, LAST_UPDATE_TIME

    print("INFO: Reloading document cache from S3...")
    new_cache = defaultdict(list)

    list_response = s3_client.list_objects_v2(
        Bucket=S3_DOCUMENTS_BUCKET, Prefix="processed_chunks/"
    )

    contents = list_response.get("Contents", [])
    if not contents:
        print("WARNING: No processed chunk files found in S3.")
        DOCUMENT_CACHE = {}
        return

    for item in contents:
        if not item["Key"].endswith(".json"):
            continue

        try:
            obj = s3_client.get_object(Bucket=S3_DOCUMENTS_BUCKET, Key=item["Key"])
            file_content = obj["Body"].read().decode("utf-8")
            chunks_data = json.loads(file_content)

            for chunk_data in chunks_data:
                source_key = chunk_data["metadata"]["source_key"]
                new_cache[source_key].append(
                    Document(
                        page_content=chunk_data["page_content"],
                        metadata=chunk_data["metadata"],
                    )
                )
        except Exception as e:
            print(f"Error loading chunk file {item['Key']}: {e}")

    DOCUMENT_CACHE = new_cache
    LAST_UPDATE_TIME = time.time()
    print(
        f"INFO: Successfully loaded {sum(len(v) for v in DOCUMENT_CACHE.values())} chunks into cache."
    )


def simple_keyword_retriever(query: str) -> list[Document]:
    """Performs a simple keyword matching across all loaded documents."""
    if not DOCUMENT_CACHE:
        return []

    query_tokens = set(re.findall(r"\b\w+\b", query.lower()))
    scored_chunks = []

    for _, doc_chunks in DOCUMENT_CACHE.items():
        for chunk in doc_chunks:
            content = chunk.page_content.lower()
            score = sum(1 for token in query_tokens if token in content)
            if score > 0:
                scored_chunks.append((score, chunk))

    scored_chunks.sort(key=lambda x: x[0], reverse=True)
    print(f"DEBUG: Retrieved {len(scored_chunks[:MAX_CONTEXT_CHUNKS])} top chunks for RAG.")
    return [chunk for score, chunk in scored_chunks[:MAX_CONTEXT_CHUNKS]]


# ---------------------------------------------------------------------------
# LLM INVOCATION WITH FALLBACK
# ---------------------------------------------------------------------------

def invoke_with_fallback(prompt: str):
    """Try Anthropic first; if blocked, fall back to Titan."""
    global llm

    try:
        print(f"DEBUG: Invoking Bedrock model {llm.model_id}...")
        response_msg = llm.invoke(prompt)
        return response_msg
    except Exception as e:
        # Detect Bedrock Anthropic access restriction
        if "use case details" in str(e) or "ResourceNotFoundException" in str(e):
            print("WARNING: Anthropic access not yet approved. Switching to Titan fallback...")
            llm = create_llm(FALLBACK_MODEL_ID)
            print(f"DEBUG: Retrying with fallback model {FALLBACK_MODEL_ID}...")
            response_msg = llm.invoke(prompt)
            return response_msg
        else:
            raise


def invoke_rag_chain(query: str, retrieved_context: list[Document]):
    """Generates the final response using Bedrock and the provided context."""
    context_text = "\n---\n".join([d.page_content for d in retrieved_context])
    source_keys = [d.metadata.get("source_key") for d in retrieved_context]

    prompt_template = f"""
You are a professional RAG (Retrieval-Augmented Generation) assistant. 
Answer the user's question ONLY based on the context provided below. 
Do not use external knowledge. If the context does not contain the answer, state that you do not know.

--- CONTEXT ---
{context_text}

--- USER QUESTION ---
{query}
"""

    try:
        response_msg = invoke_with_fallback(prompt_template)
        response_text = (
            response_msg.content
            if hasattr(response_msg, "content")
            else str(response_msg)
        )
    except Exception as e:
        print("CRITICAL BEDROCK ERROR: Model invocation failed. Traceback:")
        import traceback

        traceback.print_exc()
        raise RuntimeError(f"Bedrock invocation failed: {e}")

    return {"response": response_text, "source_documents": source_keys}


# ---------------------------------------------------------------------------
# UTILS
# ---------------------------------------------------------------------------

def get_presigned_url(file_name, file_type):
    """Generates a presigned URL for secure, direct S3 upload from the client."""
    object_key = f"incoming/{file_name}"

    url = s3_client.generate_presigned_url(
        ClientMethod="put_object",
        Params={"Bucket": S3_DOCUMENTS_BUCKET, "Key": object_key, "ContentType": file_type},
        ExpiresIn=300,
    )
    return url


def handle_system_query(query: str):
    """Checks for system keywords and returns a direct response, bypassing LLM."""
    system_keywords = ["what files", "files loaded", "documents do you have", "list files"]

    if any(keyword in query.lower() for keyword in system_keywords):
        document_list = list(DOCUMENT_CACHE.keys())

        if not document_list:
            response_text = (
                "I currently do not have any processed documents loaded in my cache."
            )
        else:
            file_names = "\n- ".join(document_list)
            response_text = (
                f"Yes, I have successfully loaded the following documents into my knowledge base:\n"
                f"- {file_names}"
            )

        print(f"INFO: Handled system query. Found {len(document_list)} files.")

        return {"response": response_text, "source_documents": document_list}

    return None  # Not a system query


# ---------------------------------------------------------------------------
# MAIN LAMBDA HANDLER
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    CORS_HEADERS = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, PUT, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, X-Amz-Date, Authorization, X-Api-Key, X-Amz-Security-Token",
    }

    http_method = event.get("requestContext", {}).get("http", {}).get("method", "UNKNOWN")
    path = event.get("rawPath", event.get("path", "/"))

    print(f"DEBUG: HTTP METHOD CHECK: {http_method}")
    print(f"DEBUG: ROUTING PATH CHECK: {path}")

    if http_method == "OPTIONS":
        return {"statusCode": 200, "headers": CORS_HEADERS}

    # --- Upload URL ---
    if path == "/default/get-upload-url" and http_method == "GET":
        print("INFO: Matched GET /default/get-upload-url")
        try:
            params = event.get("queryStringParameters", {}) or {}
            file_name = params.get("fileName")
            file_type = params.get("fileType")

            if not file_name or not file_type:
                return {
                    "statusCode": 400,
                    "headers": CORS_HEADERS,
                    "body": json.dumps({"error": "Missing fileName or fileType parameter."}),
                }

            signed_url = get_presigned_url(file_name, file_type)
            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps({"signedUrl": signed_url}),
            }
        except Exception as e:
            print(f"ERROR: Error generating presigned URL: {e}")
            return {
                "statusCode": 500,
                "headers": CORS_HEADERS,
                "body": json.dumps(
                    {"error": "Failed to generate upload URL", "details": str(e)}
                ),
            }

    # --- Query Route ---
    if path == "/default/query" and http_method == "POST":
        print("INFO: Matched POST /default/query. Starting RAG process.")

        try:
            if not DOCUMENT_CACHE:
                load_documents_from_s3()
        except Exception as e:
            print(f"ERROR: Document cache load failed: {e}")
            return {
                "statusCode": 503,
                "headers": CORS_HEADERS,
                "body": json.dumps(
                    {
                        "error": "RAG system offline. Document cache load failed.",
                        "details": str(e),
                    }
                ),
            }

        try:
            body = json.loads(event.get("body", "{}"))
            query = body.get("query")

            if not query:
                return {
                    "statusCode": 400,
                    "headers": CORS_HEADERS,
                    "body": json.dumps({"error": "Missing query parameter."}),
                }

            # --- System Query Check ---
            system_response = handle_system_query(query)
            if system_response:
                return {
                    "statusCode": 200,
                    "headers": CORS_HEADERS,
                    "body": json.dumps(system_response),
                }

            # --- RAG Retrieval ---
            context_documents = simple_keyword_retriever(query)

            if not context_documents:
                print("WARNING: No relevant context chunks found for RAG query.")
                return {
                    "statusCode": 200,
                    "headers": CORS_HEADERS,
                    "body": json.dumps(
                        {
                            "response": "I could not find any relevant documents in the knowledge base to answer your question.",
                            "source_documents": [],
                        }
                    ),
                }

            result = invoke_rag_chain(query, context_documents)
            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps(
                    {
                        "response": result["response"],
                        "source_documents": result["source_documents"],
                    }
                ),
            }

        except Exception as e:
            print(f"CRITICAL ERROR processing query: {e}")
            import traceback

            traceback.print_exc()
            return {
                "statusCode": 500,
                "headers": CORS_HEADERS,
                "body": json.dumps(
                    {"error": "Internal processing error.", "details": str(e)}
                ),
            }

    # --- Health Route ---
    if path == "/default/health" and http_method == "GET":
        status = "ok" if DOCUMENT_CACHE else "loading/degraded (Document cache empty)"
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"status": status, "service": "rag-api"}),
        }

    return {
        "statusCode": 404,
        "headers": CORS_HEADERS,
        "body": json.dumps({"error": "Resource not found"}),
    }
