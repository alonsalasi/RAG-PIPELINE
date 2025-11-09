import json
import boto3
import logging
import os
import time
import uuid
from urllib.parse import unquote_plus
from decimal import Decimal
from functools import wraps
import contextvars

# -----------------------------------------------------------
# Logging with Correlation ID
# -----------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - [%(correlation_id)s] - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Context variable for correlation ID
correlation_id_var = contextvars.ContextVar('correlation_id', default='no-correlation-id')

class CorrelationIdFilter(logging.Filter):
    def filter(self, record):
        record.correlation_id = correlation_id_var.get()
        return True

logger.addFilter(CorrelationIdFilter())

# -----------------------------------------------------------
# Security Utils
# -----------------------------------------------------------
def sanitize_for_logging(text, max_length=100):
    """Sanitize text for logging to prevent log injection attacks."""
    if not text:
        return "[EMPTY]"
    # Convert to string and remove control characters
    text_str = str(text)
    # Remove all control characters including newlines, tabs, etc.
    safe = ''.join(c if c.isprintable() and ord(c) >= 32 else '_' for c in text_str)
    # Truncate and add indicator if truncated
    if len(safe) > max_length:
        return safe[:max_length-3] + "..."
    return safe

def validate_filename(filename):
    if not filename or not isinstance(filename, str):
        raise ValueError("Invalid filename")
    filename = filename.strip()
    if not filename or filename.startswith('.') or '/' in filename or '\\' in filename:
        raise ValueError("Invalid filename")
    if len(filename) > 255:
        raise ValueError("Filename too long")
    return filename

def retry_with_backoff(max_retries=3):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    time.sleep(2 ** attempt)
        return wrapper
    return decorator

# -----------------------------------------------------------
# AWS Setup
# -----------------------------------------------------------
from botocore.client import Config

# Thread-safe client initialization
_s3_client = None
_bedrock_client = None
_embeddings_client = None
_faiss_cache = {}

def get_s3_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client(
            "s3", 
            config=Config(
                signature_version='s3v4', 
                connect_timeout=3, 
                read_timeout=30,
                max_pool_connections=50,
                retries={'max_attempts': 2}
            )
        )
    return _s3_client

# Track when client was created to detect stale connections
_bedrock_client_created_at = None
CLIENT_MAX_AGE_SECONDS = 300  # Refresh client every 5 minutes

def get_bedrock_client():
    """Get Bedrock client with optimized configuration and auto-refresh."""
    global _bedrock_client, _bedrock_client_created_at
    
    # Refresh client if it's too old (prevents stale agent version issues)
    current_time = time.time()
    if _bedrock_client is not None and _bedrock_client_created_at is not None:
        age = current_time - _bedrock_client_created_at
        if age > CLIENT_MAX_AGE_SECONDS:
            logger.info(f"Bedrock client is {age:.0f}s old, refreshing...")
            _bedrock_client = None
    
    if _bedrock_client is None:
        region = os.getenv("AWS_REGION")
        if not region:
            raise ValueError("AWS_REGION must be configured")
        _bedrock_client = boto3.client(
            "bedrock-agent-runtime",
            region_name=region,
            config=Config(
                connect_timeout=2, 
                read_timeout=30,
                max_pool_connections=20,
                retries={'max_attempts': 1}
            )
        )
        _bedrock_client_created_at = current_time
        logger.info(f"Bedrock client initialized: {region}")
    return _bedrock_client

def get_embeddings_client():
    """Get embeddings client with proper error handling."""
    global _embeddings_client
    if _embeddings_client is None:
        from langchain_aws import BedrockEmbeddings
        region = os.getenv("AWS_REGION")
        if not region:
            raise ValueError("AWS_REGION must be configured")
        model_id = os.getenv("EMBEDDINGS_MODEL_ID", "cohere.embed-multilingual-v3")
        _embeddings_client = BedrockEmbeddings(model_id=model_id, region_name=region)
        logger.info(f"Embeddings client initialized: {model_id}")
    return _embeddings_client

# Get S3 bucket from environment
BUCKET = os.getenv("S3_BUCKET")
if not BUCKET:
    logger.error("S3_BUCKET environment variable not configured")
    raise ValueError("S3_BUCKET environment variable must be set")

# Track index timestamp to detect updates
_index_s3_timestamp = None

@retry_with_backoff(max_retries=2)
def preload_master_index(force_reload=False):
    """Preload master FAISS index with automatic update detection."""
    from langchain_community.vectorstores import FAISS
    import shutil
    from datetime import datetime
    
    global _index_s3_timestamp
    cache_key = "master_index"
    cache_dir = "/tmp/master_index"
    s3_client = get_s3_client()
    
    # Check if S3 index was updated (new upload)
    try:
        s3_obj = s3_client.head_object(Bucket=BUCKET, Key="vector_store/master/index.faiss")
        s3_last_modified = s3_obj['LastModified'].timestamp()
        
        # If we have a cached index, check if S3 version is newer
        if cache_key in _faiss_cache and _index_s3_timestamp is not None:
            if s3_last_modified > _index_s3_timestamp:
                logger.info(f"S3 index updated (cached: {datetime.fromtimestamp(_index_s3_timestamp)}, S3: {datetime.fromtimestamp(s3_last_modified)}), reloading...")
                del _faiss_cache[cache_key]
            else:
                logger.info("Master index cached and up-to-date")
                return
        elif cache_key in _faiss_cache:
            logger.info("Master index already cached")
            return
            
    except s3_client.exceptions.ClientError as e:
        if e.response.get('Error', {}).get('Code') == '404':
            logger.info("No master index exists yet")
            return
        logger.warning(f"Error checking S3 index timestamp: {type(e).__name__}")
    
    # Timestamp check is now done inside preload_master_index
    try:
        s3_client.head_object(Bucket=BUCKET, Key="vector_store/master/index.faiss")
    except s3_client.exceptions.ClientError as e:
        if e.response.get('Error', {}).get('Code') == '404':
            logger.info("No master index to preload")
        else:
            logger.warning(f"Error checking master index: {type(e).__name__}")
        return
    except Exception as e:
        logger.error(f"Unexpected error: {type(e).__name__}")
        return
    
    if os.path.exists(cache_dir):
        shutil.rmtree(cache_dir)
    
    os.makedirs(cache_dir, exist_ok=True)
    
    index_file = os.path.join(cache_dir, "index.faiss")
    pkl_file = os.path.join(cache_dir, "index.pkl")
    
    start_time = time.time()
    # Download files in parallel for faster startup
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future1 = executor.submit(s3_client.download_file, BUCKET, "vector_store/master/index.faiss", index_file)
        future2 = executor.submit(s3_client.download_file, BUCKET, "vector_store/master/index.pkl", pkl_file)
        concurrent.futures.wait([future1, future2])
    
    embeddings = get_embeddings_client()
    master_index = FAISS.load_local(cache_dir, embeddings, allow_dangerous_deserialization=True)
    _faiss_cache[cache_key] = master_index
    
    # Store S3 timestamp for future comparisons
    try:
        s3_obj = s3_client.head_object(Bucket=BUCKET, Key="vector_store/master/index.faiss")
        _index_s3_timestamp = s3_obj['LastModified'].timestamp()
    except:
        _index_s3_timestamp = time.time()
    
    logger.info(f"Preloaded master index: {master_index.index.ntotal} vectors in {time.time() - start_time:.2f}s")

try:
    preload_master_index()
except Exception as e:
    logger.error(f"Startup preload failed: {type(e).__name__}")


def list_all_s3_objects(bucket, prefix, max_keys=1000):
    """List all S3 objects with pagination support and limits."""
    if not bucket or not isinstance(bucket, str):
        raise ValueError("Invalid bucket name")
    if not prefix or not isinstance(prefix, str):
        raise ValueError("Invalid prefix")
    
    s3_client = get_s3_client()
    objects = []
    continuation_token = None
    total_fetched = 0
    
    while total_fetched < max_keys:
        params = {
            'Bucket': bucket,
            'Prefix': prefix,
            'MaxKeys': min(1000, max_keys - total_fetched)
        }
        if continuation_token:
            params['ContinuationToken'] = continuation_token
        
        response = s3_client.list_objects_v2(**params)
        batch = response.get('Contents', [])
        objects.extend(batch)
        total_fetched += len(batch)
        
        if not response.get('IsTruncated', False) or total_fetched >= max_keys:
            break
        continuation_token = response.get('NextContinuationToken')
    
    return objects

def batch_delete_s3_objects(bucket, keys):
    """Delete multiple S3 objects in batches of 1000."""
    if not keys:
        return 0
    if not bucket or not isinstance(bucket, str):
        raise ValueError("Invalid bucket name")
    
    s3_client = get_s3_client()
    deleted_count = 0
    
    for i in range(0, len(keys), 1000):
        batch = keys[i:i+1000]
        delete_dict = {'Objects': [{'Key': k} for k in batch], 'Quiet': True}
        try:
            s3_client.delete_objects(Bucket=bucket, Delete=delete_dict)
            deleted_count += len(batch)
        except Exception as e:
            logger.error(f"Batch delete failed: {type(e).__name__}")
            raise
    
    return deleted_count

# -----------------------------------------------------------
# Utilities
# -----------------------------------------------------------
def cors_response(body=None, status=200):
    """Return a standard CORS-enabled response."""
    return {
        "statusCode": status,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        },
        "body": json.dumps(body or {}),
    }


# -----------------------------------------------------------
# /get-upload-url
# -----------------------------------------------------------
def handle_get_upload_url():
    """Generate a presigned S3 URL for direct PDF upload."""
    try:
        timestamp = int(time.time())
        key = f"uploads/upload_{timestamp}.pdf"
        s3_client = get_s3_client()
        url = s3_client.generate_presigned_url(
            "put_object",
            Params={"Bucket": BUCKET, "Key": key, "ContentType": "application/pdf"},
            ExpiresIn=7200,
        )
        logger.info(f"Upload URL generated | Key: {sanitize_for_logging(key)} | Expires: 7200s")
        return cors_response({"uploadUrl": url, "key": key})
    except Exception as e:
        logger.error(f"Upload URL generation failed | Error: {type(e).__name__} | Details: {str(e)[:100]}")
        return cors_response({"error": "Failed to generate upload URL"}, 500)


# -----------------------------------------------------------
# /list-files
# -----------------------------------------------------------
def handle_list_files():
    """List processed PDFs available for querying."""
    try:
        logger.info("Listing processed files | Bucket: {BUCKET} | Prefix: processed/")
        s3_client = get_s3_client()
        response = s3_client.list_objects_v2(Bucket=BUCKET, Prefix="processed/", MaxKeys=1000)
        files = []
        if "Contents" in response:
            for obj in response["Contents"]:
                key = obj["Key"]
                if key.endswith(".json"):
                    filename = key.split("/")[-1].replace(".json", "")
                    files.append({
                        "filename": filename,
                        "lastModified": obj["LastModified"].isoformat(),
                        "size": obj["Size"]
                    })
        
        logger.info(f"List files complete | Count: {len(files)} | Truncated: {response.get('IsTruncated', False)}")
        return cors_response({"files": files})
    except Exception as e:
        logger.error(f"List files failed | Error: {type(e).__name__} | Details: {str(e)[:100]}")
        return cors_response({"error": "Failed to list files"}, 500)


# -----------------------------------------------------------
# /delete-file
# -----------------------------------------------------------
def handle_delete_file(filename):
    """Delete a processed PDF and its associated data."""
    try:
        filename = validate_filename(filename)
        logger.info(f"Delete operation started | File: {sanitize_for_logging(filename)}")
        
        s3_client = get_s3_client()
        
        # Delete processed JSON
        processed_key = f"processed/{filename}.json"
        try:
            s3_client.delete_object(Bucket=BUCKET, Key=processed_key)
            logger.info(f"Deleted processed JSON | Key: {sanitize_for_logging(processed_key)}")
        except Exception as e:
            logger.warning(f"Could not delete processed | Key: {processed_key} | Error: {type(e).__name__}")
        
        # Delete uploads (limit search)
        upload_objects = list_all_s3_objects(BUCKET, f"uploads/{filename}", max_keys=100)
        logger.info(f"Found {len(upload_objects)} upload objects")
        for obj in upload_objects:
            try:
                s3_client.delete_object(Bucket=BUCKET, Key=obj["Key"])
            except Exception as e:
                logger.warning(f"Delete upload failed | Key: {obj['Key']} | Error: {type(e).__name__}")
        
        # Delete images
        image_objects = list_all_s3_objects(BUCKET, f"images/{filename}/", max_keys=500)
        image_keys = [obj["Key"] for obj in image_objects]
        if image_keys:
            deleted_count = batch_delete_s3_objects(BUCKET, image_keys)
            logger.info(f"Deleted images | Count: {deleted_count} | File: {filename}")
        
        # Delete vector store data
        vector_objects = list_all_s3_objects(BUCKET, f"vector_store/{filename}/", max_keys=100)
        vector_keys = [obj["Key"] for obj in vector_objects]
        if vector_keys:
            deleted_count = batch_delete_s3_objects(BUCKET, vector_keys)
            logger.info(f"Deleted vector objects | Count: {deleted_count} | File: {filename}")
        
        # Clear FAISS cache
        if filename in _faiss_cache:
            del _faiss_cache[filename]
            logger.info(f"Cleared FAISS cache | File: {sanitize_for_logging(filename)}")
        
        logger.info(f"Delete operation complete | File: {filename}")
        return cors_response({"message": f"Successfully deleted {filename}"})
    except ValueError as e:
        logger.warning(f"Invalid filename | Error: {type(e).__name__} | Details: {str(e)[:100]}")
        return cors_response({"error": str(e)}, 400)
    except Exception as e:
        logger.error(f"Delete failed | File: {filename} | Error: {type(e).__name__} | Details: {str(e)[:100]}")
        return cors_response({"error": "Failed to delete file"}, 500)


# -----------------------------------------------------------
# Optimized Search Function
# -----------------------------------------------------------
def optimized_search(query, top_k=30):
    """Intelligent search using semantic similarity."""
    try:
        # Use cached index first
        cache_key = "master_index"
        if cache_key in _faiss_cache:
            master_index = _faiss_cache[cache_key]
        else:
            # Fallback: try to load from disk cache
            from langchain_community.vectorstores import FAISS
            cache_dir = "/tmp/master_index"
            
            if os.path.exists(os.path.join(cache_dir, "index.faiss")):
                # Load from existing disk cache
                embeddings = get_embeddings_client()
                master_index = FAISS.load_local(cache_dir, embeddings, allow_dangerous_deserialization=True)
                _faiss_cache[cache_key] = master_index
                
                # Store S3 timestamp
                try:
                    s3_obj = s3_client.head_object(Bucket=BUCKET, Key="vector_store/master/index.faiss")
                    _index_s3_timestamp = s3_obj['LastModified'].timestamp()
                except:
                    _index_s3_timestamp = time.time()
                    
                logger.info("Loaded index from disk cache")
            else:
                # Last resort: download and cache
                preload_master_index()
                if cache_key not in _faiss_cache:
                    logger.error("Failed to load master index")
                    return []
                master_index = _faiss_cache[cache_key]
        
        # Direct semantic search with higher k for better recall
        start_time = time.time()
        results = master_index.similarity_search_with_score(query, k=top_k)
        search_time = time.time() - start_time
        
        # Minimal result formatting for speed
        formatted_results = []
        for doc, semantic_score in results:
            formatted_results.append({
                'content': doc.page_content,
                'metadata': doc.metadata,
                'semantic_score': float(semantic_score)
            })
        
        logger.info(f"Semantic search: {len(results)} results in {search_time:.3f}s")
        return formatted_results
        
    except Exception as e:
        logger.error(f"Search failed: {type(e).__name__}")
        return []


# -----------------------------------------------------------
# /search
# -----------------------------------------------------------
def handle_search(query):
    """Handle search requests with intelligent filtering."""
    try:
        if not query or not query.strip():
            return cors_response({"error": "Query is required"}, 400)
        
        query = query.strip()
        logger.info(f"Search started | Query: {sanitize_for_logging(query)} | Length: {len(query)}")
        
        results = optimized_search(query, top_k=15)
        
        logger.info(f"Search complete | Results: {len(results)} | Query: {sanitize_for_logging(query)[:50]}")
        return cors_response({
            "results": results,
            "query": query,
            "total": len(results)
        })
        
    except Exception as e:
        logger.error(f"Search failed | Query: {sanitize_for_logging(query)[:50]} | Error: {type(e).__name__} | Details: {str(e)[:100]}")
        return cors_response({"error": "Search failed"}, 500)


# -----------------------------------------------------------
# Bedrock Agent Integration
# -----------------------------------------------------------
def handle_agent_query(query, session_id=None):
    """Handle queries using Bedrock Agent with search integration."""
    try:
        if not query or not query.strip():
            return cors_response({"error": "Query is required"}, 400)
        
        query = query.strip()
        if not session_id:
            session_id = str(uuid.uuid4())
        
        logger.info(f"Processing agent query: {sanitize_for_logging(query)} (session: {sanitize_for_logging(session_id)})")
        
        # Get agent configuration from environment
        agent_id = os.getenv("BEDROCK_AGENT_ID")
        agent_alias_id = os.getenv("BEDROCK_AGENT_ALIAS_ID")
        
        if not agent_id or not agent_alias_id:
            logger.error("Bedrock agent configuration missing")
            return cors_response({"error": "Agent configuration not found"}, 500)
        
        bedrock_client = get_bedrock_client()
        
        # Invoke the agent
        response = bedrock_client.invoke_agent(
            agentId=agent_id,
            agentAliasId=agent_alias_id,
            sessionId=session_id,
            inputText=query
        )
        
        # Process the response stream
        response_text = ""
        for event in response.get('completion', []):
            if 'chunk' in event:
                chunk = event['chunk']
                if 'bytes' in chunk:
                    response_text += chunk['bytes'].decode('utf-8')
        
        logger.info(f"Agent response generated (length: {len(response_text)})")
        
        return cors_response({
            "response": response_text,
            "sessionId": session_id,
            "query": query
        })
        
    except Exception as e:
        logger.error(f"Agent query failed: {sanitize_for_logging(str(e))}")
        return cors_response({"error": "Agent query failed"}, 500)


# -----------------------------------------------------------
# Lambda Handler
# -----------------------------------------------------------
def lambda_handler(event, context):
    """Main Lambda handler with comprehensive error handling."""
    try:
        logger.info(f"Received event: {sanitize_for_logging(json.dumps(event, default=str))}")
        
        # Handle CORS preflight
        if event.get("httpMethod") == "OPTIONS":
            return cors_response()
        
        # Extract path and method
        path = event.get("path", "")
        method = event.get("httpMethod", "")
        
        # Parse body for POST requests
        body = {}
        if method == "POST" and event.get("body"):
            try:
                body = json.loads(event["body"])
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON in request body: {sanitize_for_logging(str(e))}")
                return cors_response({"error": "Invalid JSON"}, 400)
        
        # Route requests
        if path == "/get-upload-url" and method == "GET":
            return handle_get_upload_url()
        
        elif path == "/list-files" and method == "GET":
            return handle_list_files()
        
        elif path.startswith("/delete-file/") and method == "DELETE":
            filename = unquote_plus(path.split("/delete-file/")[1])
            return handle_delete_file(filename)
        
        elif path == "/search" and method == "POST":
            query = body.get("query", "")
            return handle_search(query)
        
        elif path == "/agent" and method == "POST":
            query = body.get("query", "")
            session_id = body.get("sessionId")
            return handle_agent_query(query, session_id)
        
        else:
            logger.warning(f"Unknown endpoint: {sanitize_for_logging(path)} {sanitize_for_logging(method)}")
            return cors_response({"error": "Endpoint not found"}, 404)
    
    except Exception as e:
        logger.error(f"Unhandled error in lambda_handler: {sanitize_for_logging(str(e))}")
        return cors_response({"error": "Internal server error"}, 500)
        for item in response.get("Contents", []):
            key = item["Key"]
            if key.lower().endswith(".pdf"):
                files.append(os.path.basename(key))
        logger.info(f" Listed {len(files)} processed PDFs.")
        return cors_response({"files": files})
    except Exception as e:
        logger.error(f" Failed to list files: {type(e).__name__}")
        return cors_response({"error": "Failed to list files"}, 500)


# -----------------------------------------------------------
# /agent-query
# -----------------------------------------------------------
def handle_get_upload_url_api(event):
    """API Gateway handler for generating upload URLs."""
    try:
        body_str = event.get("body") or "{}"
        try:
            body = json.loads(body_str) if body_str else {}
        except json.JSONDecodeError:
            return cors_response({"error": "Invalid JSON in request body"}, 400)
        
        file_name = body.get("fileName", f"upload_{int(time.time())}.pdf")
        
        try:
            file_name = validate_filename(file_name)
        except ValueError as e:
            return cors_response({"error": str(e)}, 400)
        
        allowed_extensions = ('.pdf', '.pptx', '.docx', '.xlsx')
        if not file_name.lower().endswith(allowed_extensions):
            return cors_response({"error": "Only PDF, PPTX, DOCX, and XLSX files are allowed"}, 400)
        
        base_name = os.path.splitext(file_name)[0] if '.' in file_name else file_name
        
        key = f"uploads/{file_name}"
        s3_client = get_s3_client()
        
        # Determine content type based on file extension
        content_type_map = {
            '.pdf': 'application/pdf',
            '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        }
        
        file_ext = os.path.splitext(file_name)[1].lower()
        content_type = content_type_map.get(file_ext, 'application/octet-stream')
        
        signed_url = s3_client.generate_presigned_url(
            "put_object",
            Params={"Bucket": BUCKET, "Key": key, "ContentType": content_type},
            ExpiresIn=3600
        )
        logger.info(f" Generated upload URL for key: {key}")
        return cors_response({"signedUrl": signed_url, "fileName": file_name})
    except Exception as e:
        logger.error(f" Upload URL error: {type(e).__name__}", exc_info=True)
        return cors_response({"error": "Upload URL generation failed"}, 500)

def handle_list_files_api(event):
    """API Gateway handler for listing files."""
    try:
        objects = list_all_s3_objects(BUCKET, "processed/")
        filenames = []
        for obj in objects:
            if obj["Key"].endswith(".json"):
                filenames.append(os.path.basename(obj["Key"]))
        return cors_response({"filenames": filenames})
    except Exception as e:
        logger.error(f" List files error: {type(e).__name__}")
        return cors_response({"error": "Failed to list files"}, 500)

def get_document_context(metadata, base_name):
    """Extract rich document-level context for chunk enrichment."""
    context_parts = [f"Document: {base_name}"]
    
    # Add text preview summary
    text_preview = metadata.get('text_preview', '').strip()
    if text_preview:
        first_line = text_preview.split('\n')[0][:80].strip()
        if first_line:
            context_parts.append(f"Subject: {first_line}")
    
    # Add visual context from first image
    images = metadata.get('images', [])
    if images:
        first_img = images[0].get('description', '')
        if 'BRAND:' in first_img:
            brand = first_img.split('BRAND:')[1].split('\n')[0].strip()
            if brand and brand.lower() != 'none visible':
                context_parts.append(f"Brand: {brand}")
    
    return " | ".join(context_parts)

def rebuild_master_index():
    """Rebuild master index from all remaining processed documents."""
    try:
        from langchain_community.vectorstores import FAISS
        from langchain.docstore.document import Document
        import tempfile
        
        logger.info(" Rebuilding master index...")
        
        # Get all processed documents
        processed_objects = list_all_s3_objects(BUCKET, "processed/")
        if not processed_objects:
            logger.info(" No documents to index, deleting master index")
            try:
                s3_client = get_s3_client()
                s3_client.delete_object(Bucket=BUCKET, Key="vector_store/master/index.faiss")
                s3_client.delete_object(Bucket=BUCKET, Key="vector_store/master/index.pkl")
            except:
                pass
            # Clear cache
            if "master_index" in _faiss_cache:
                del _faiss_cache["master_index"]
            return
        
        embeddings = get_embeddings_client()
        all_docs = []
        
        # Collect all documents from processed files
        for obj in processed_objects:
            if not obj['Key'].endswith('.json'):
                continue
            
            try:
                # Get processed metadata
                s3_client = get_s3_client()
                response = s3_client.get_object(Bucket=BUCKET, Key=obj['Key'])
                metadata = json.loads(response['Body'].read().decode('utf-8'))
                
                source_file = metadata.get('source_file', '')
                base_name = os.path.basename(source_file).replace('.pdf', '')
                
                # Get rich document context
                context_prefix = get_document_context(metadata, base_name)
                
                # Get full text from metadata (not just preview)
                full_text = metadata.get('full_text', metadata.get('text_preview', ''))
                if full_text:
                    # Use smaller chunks for better ranking
                    from langchain.text_splitter import RecursiveCharacterTextSplitter
                    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
                    chunks = splitter.split_text(full_text)
                    
                    for i, chunk in enumerate(chunks):
                        doc = Document(
                            page_content=f"Document: {base_name}\n{chunk}",
                            metadata={
                                "source": base_name,
                                "chunk_id": i
                            }
                        )
                        all_docs.append(doc)
                
                # Add image documents
                images = metadata.get('images', [])
                for img_meta in images:
                    img_desc = img_meta.get('description', 'Image')
                    s3_key = img_meta.get('s3_key', '')
                    
                    # Add document name prefix to help with ranking
                    page_content = f"Document: {base_name}\nImage from page {img_meta['page']}: {img_desc}\nIMAGE_URL:{s3_key}|PAGE:{img_meta['page']}|SOURCE:{base_name}"
                    
                    img_doc = Document(
                        page_content=page_content,
                        metadata={
                            "source": base_name,
                            "type": "image",
                            "page": img_meta['page'],
                            "image_url": img_meta.get('url', ''),
                            "s3_key": s3_key,
                            "context_summary": context_prefix
                        }
                    )
                    all_docs.append(img_doc)
                    
            except Exception as e:
                logger.error(f" Failed to process {obj['Key']}: {e}")
        
        if not all_docs:
            logger.warning(" No documents collected for indexing")
            return
        
        logger.info(f" Creating master index with {len(all_docs)} documents")
        
        # Create new master index
        with tempfile.TemporaryDirectory() as tmpdir:
            master_store = FAISS.from_documents(all_docs, embeddings)
            master_store.save_local(tmpdir)
            
            # Upload to S3
            s3_client = get_s3_client()
            s3_client.upload_file(os.path.join(tmpdir, "index.faiss"), BUCKET, "vector_store/master/index.faiss")
            s3_client.upload_file(os.path.join(tmpdir, "index.pkl"), BUCKET, "vector_store/master/index.pkl")
        
        # Clear cache to force reload
        if "master_index" in _faiss_cache:
            del _faiss_cache["master_index"]
        
        logger.info(" Master index rebuilt successfully")
        
    except Exception as e:
        logger.error(f" Failed to rebuild master index: {e}")
        raise

def handle_delete_file_api(event):
    """API Gateway handler for deleting files."""
    try:
        params = event.get("queryStringParameters") or {}
        display_name = params.get("fileName")
        
        try:
            display_name = validate_filename(display_name)
        except (ValueError, TypeError) as e:
            return cors_response({"error": "Invalid fileName"}, 400)
        
        logger.info(f" Deleting file: {sanitize_for_logging(display_name)}")
        base_name = display_name.replace('.json', '') if display_name.endswith('.json') else display_name
        
        # Collect all keys to delete
        keys_to_delete = []
        
        # Add JSON marker
        keys_to_delete.append(f"processed/{base_name}.json")
        
        # Collect PDFs
        try:
            pdf_objects = list_all_s3_objects(BUCKET, f"uploads/{base_name}")
            for obj in pdf_objects:
                if obj['Key'].startswith(f"uploads/{base_name}."):
                    keys_to_delete.append(obj['Key'])
        except Exception as e:
            logger.error(f" Failed to list PDFs: {e}")
        
        # Collect images
        try:
            image_objects = list_all_s3_objects(BUCKET, f"images/{base_name}/")
            keys_to_delete.extend([obj['Key'] for obj in image_objects])
        except Exception as e:
            logger.error(f" Failed to list images: {e}")
        
        # Batch delete all collected keys
        deleted_count = batch_delete_s3_objects(BUCKET, keys_to_delete)
        logger.info(f" Deleted {deleted_count} objects for {base_name}")
        
        # Rebuild master index without this document
        try:
            rebuild_master_index()
            logger.info(" Master index rebuilt after deletion")
        except Exception as e:
            logger.error(f" Failed to rebuild master index: {e}")
            # Don't fail the delete operation if rebuild fails
        
        return cors_response({"message": f"{base_name} deleted successfully"})
    except Exception as e:
        logger.error(f" Delete file error: {type(e).__name__}")
        return cors_response({"error": "Failed to delete file"}, 500)

def handle_cancel_upload_api(event):
    """API Gateway handler for cancelling uploads and cleaning up partial files."""
    try:
        params = event.get("queryStringParameters") or {}
        file_name = params.get("fileName")
        
        try:
            file_name = validate_filename(file_name)
        except (ValueError, TypeError) as e:
            return cors_response({"error": "Invalid fileName"}, 400)
        
        logger.info(f" Cancelling upload: {sanitize_for_logging(file_name)}")
        base_name = os.path.splitext(file_name)[0] if '.' in file_name else file_name
        
        # Create cancellation marker FIRST to stop Lambda processing
        try:
            s3_client = get_s3_client()
            s3_client.put_object(
                Bucket=BUCKET,
                Key=f"cancelled/{base_name}.txt",
                Body=f"Cancelled at {time.time()}",
                ContentType="text/plain"
            )
            logger.info(f" Created cancellation marker")
        except Exception as e:
            logger.error(f" Failed to create cancellation marker: {e}")
        
        # Collect all keys to delete
        keys_to_delete = []
        
        # Collect uploads
        try:
            upload_objects = list_all_s3_objects(BUCKET, f"uploads/{base_name}")
            keys_to_delete.extend([obj['Key'] for obj in upload_objects])
        except Exception as e:
            logger.error(f" Failed to list uploads: {e}")
        
        # Collect processed
        try:
            processed_objects = list_all_s3_objects(BUCKET, f"processed/{base_name}")
            keys_to_delete.extend([obj['Key'] for obj in processed_objects])
        except Exception as e:
            logger.error(f" Failed to list processed: {e}")
        
        # Collect images
        try:
            image_objects = list_all_s3_objects(BUCKET, f"images/{base_name}/")
            keys_to_delete.extend([obj['Key'] for obj in image_objects])
        except Exception as e:
            logger.error(f" Failed to list images: {e}")
        
        # Note: No need to delete vector store - using master index now
        
        # Add cancellation marker to delete list
        keys_to_delete.append(f"cancelled/{base_name}.txt")
        
        # Batch delete all collected keys
        deleted_count = batch_delete_s3_objects(BUCKET, keys_to_delete)
        logger.info(f" Total files deleted: {deleted_count}")
        
        return cors_response({"message": f"Cancelled and deleted {deleted_count} files for {base_name}"})
    except Exception as e:
        logger.error(f" Cancel upload error: {type(e).__name__}")
        return cors_response({"error": "Failed to cancel upload"}, 500)





def handle_search_action(event):
    """Intelligent search using semantic similarity without hardcoded rules."""
    search_start = time.time()
    try:
        logger.info(f"🔍 SEARCH ACTION CALLED - Agent is searching PDFs")
        parse_start = time.time()
        request_body = event.get("requestBody", {})
        content = request_body.get("content", {})
        app_json = content.get("application/json", {})
        properties = app_json.get("properties", [])
        
        query = ""
        for prop in properties:
            if prop.get("name") == "query":
                query = prop.get("value", "")
                break
        
        # Get original user input to check for visual triggers
        original_input = event.get("inputText", "")
        logger.info(f"🔍 ORIGINAL INPUT: {sanitize_for_logging(original_input)}")
        logger.info(f"🔍 SEARCH QUERY: {sanitize_for_logging(query)}")
        logger.info(f"⏱️ SEARCH: Parse request took {time.time() - parse_start:.3f}s")
        
        if not query.strip():
            return {
                "messageVersion": "1.0",
                "response": {
                    "actionGroup": event.get("actionGroup", "LambdaTools"),
                    "apiPath": "/search",
                    "httpMethod": "POST",
                    "httpStatusCode": 200,
                    "responseBody": {"application/json": {"body": json.dumps({"result": "Please specify what you're looking for."})}}
                }
            }
        
        from langchain_community.vectorstores import FAISS
        
        # Use cached index
        cache_start = time.time()
        cache_key = "master_index"
        if cache_key in _faiss_cache:
            master_index = _faiss_cache[cache_key]
            logger.info(f"⏱️ SEARCH: Cache hit took {time.time() - cache_start:.3f}s")
        else:
            logger.info("⏱️ SEARCH: Cache miss, loading index...")
            preload_master_index()
            logger.info(f"⏱️ SEARCH: Index load took {time.time() - cache_start:.3f}s")
            if cache_key not in _faiss_cache:
                return {
                    "messageVersion": "1.0",
                    "response": {
                        "actionGroup": event.get("actionGroup", "LambdaTools"),
                        "apiPath": "/search",
                        "httpMethod": "POST",
                        "httpStatusCode": 200,
                        "responseBody": {"application/json": {"body": json.dumps({"result": "No documents have been uploaded yet. Please upload PDF files first to enable search functionality. You can upload files using the upload feature in the application."})}}
                    }
                }
            master_index = _faiss_cache[cache_key]
        
        # 1. Smart Intent Detection - works for ANY subject
        query_lower = query.lower()
        original_lower = original_input.lower() if original_input else query_lower
        
        # Question words = user wants information (TEXT)
        question_words = ['what', 'how', 'why', 'when', 'where', 'which', 'who', 'whose', 'whom']
        # Comparison/analysis = user wants details (TEXT)
        analysis_words = ['compare', 'difference', 'versus', 'vs', 'between', 'analyze', 'explain', 'describe', 'tell', 'list', 'summarize']
        # Visual commands = user wants to see (IMAGES)
        visual_commands = ['show me', 'display', 'picture of', 'photo of', 'image of', 'look at', 'see the', 'view the']
        
        # Count intent signals
        text_signals = 0
        image_signals = 0
        
        # Check for question words at start (strong text signal)
        first_word = query_lower.split()[0] if query_lower.split() else ''
        if first_word in question_words:
            text_signals += 2
        
        # Check for analysis/comparison words
        if any(word in original_lower for word in analysis_words):
            text_signals += 2
        
        # Check for visual commands
        if any(cmd in original_lower for cmd in visual_commands):
            image_signals += 2
        
        # Check for standalone visual words (weaker signal)
        if any(word in original_lower.split() for word in ['picture', 'photo', 'image', 'drawing']):
            image_signals += 1
        
        # Decision based on signal strength
        if text_signals > image_signals:
            wants_text = True
            wants_images = False
            logger.info(f"📄 Intent: TEXT (signals: text={text_signals}, image={image_signals})")
        elif image_signals > text_signals:
            wants_images = True
            wants_text = False
            logger.info(f"🖼️ Intent: IMAGES (signals: text={text_signals}, image={image_signals})")
        else:
            # Equal or no strong signals = hybrid
            wants_text = True
            wants_images = True
            logger.info(f"🔄 Intent: HYBRID (signals: text={text_signals}, image={image_signals})")
        
        # 2. Wide Retrieval with fuzzy matching
        vector_start = time.time()
        raw_results = master_index.similarity_search_with_score(query, k=60)
        logger.info(f"⏱️ SEARCH: Vector search (k=60) took {time.time() - vector_start:.3f}s, found {len(raw_results)} results")
        
        # Apply fuzzy matching to boost relevant results
        from difflib import SequenceMatcher
        
        def fuzzy_score(text1, text2):
            """Calculate fuzzy similarity between two strings (0-1)."""
            return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()
        
        # Extract key terms from query (ignore stop words)
        stop_words = {'show', 'me', 'the', 'a', 'an', 'in', 'of', 'with', 'from', 'to', 'for', 'and', 'or', 'image', 'picture', 'photo', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'should', 'could', 'may', 'might', 'must', 'can', 'this', 'that', 'these', 'those', 'it', 'its', 'they', 'them', 'their'}
        query_terms = [w for w in query_lower.split() if w not in stop_words and len(w) > 2]
        
        # Re-score results with fuzzy matching boost
        fuzzy_results = []
        for doc, semantic_score in raw_results:
            content_lower = doc.page_content.lower()
            
            # Calculate fuzzy match score for each query term
            fuzzy_boost = 0
            for term in query_terms:
                # Check for exact match first
                if term in content_lower:
                    fuzzy_boost += 1.0
                else:
                    # Check for fuzzy match (e.g., "chery" matches "cherry")
                    words_in_content = content_lower.split()
                    best_match = max([fuzzy_score(term, word) for word in words_in_content] + [0])
                    if best_match > 0.8:  # 80% similarity threshold
                        fuzzy_boost += best_match
                        logger.info(f"🔍 Fuzzy match: '{term}' → best_match={best_match:.2f}")
            
            # Adjust semantic score with fuzzy boost (lower score = better)
            adjusted_score = semantic_score - (fuzzy_boost * 0.2)
            fuzzy_results.append((doc, adjusted_score, semantic_score))
        
        # Sort by adjusted score
        fuzzy_results.sort(key=lambda x: x[1])
        raw_results = [(doc, adj_score) for doc, adj_score, _ in fuzzy_results]
        
        # 3. Separate Candidates
        text_candidates = []
        image_candidates = []
        for doc, score in raw_results:
            if doc.metadata.get('type') == 'image':
                image_candidates.append((doc, score))
            else:
                text_candidates.append((doc, score))
        
        # 4. Select Best Results based on Intent
        final_results = []
        
        if wants_images and not wants_text:
            # PURE IMAGE QUERY
            
            # Apply attribute filtering for images (colors, sizes, etc.)
            color_words = ['red', 'blue', 'black', 'white', 'gray', 'grey', 'green', 'yellow', 'orange', 'silver', 'brown', 'purple', 'pink', 'gold', 'beige', 'tan']
            size_words = ['large', 'small', 'big', 'tiny', 'huge', 'medium']
            attribute_words = color_words + size_words
            query_attributes = [attr for attr in attribute_words if attr in query_lower]
            
            # Get meaningful query words (not stop words or attributes)
            query_words = [w for w in query_lower.split() if w not in stop_words and w not in attribute_words and len(w) > 2]
            
            scored_images = []
            for doc, semantic_score in image_candidates:
                content_lower = doc.page_content.lower()
                match_score = 0
                
                # Boost images that match requested attributes
                if query_attributes:
                    matching_attrs = sum(1 for attr in query_attributes if attr in content_lower)
                    if matching_attrs > 0:
                        match_score += matching_attrs * 30
                    else:
                        match_score -= 20  # Penalize if no attributes match
                
                # Boost images that match subject words
                if query_words:
                    word_matches = sum(1 for word in query_words if word in content_lower)
                    match_score += word_matches * 10
                
                combined_score = semantic_score - (match_score * 0.1)
                scored_images.append((doc, combined_score))
            
            scored_images.sort(key=lambda x: x[1])
            final_results.extend(scored_images[:10])
            
        elif wants_text and not wants_images:
            # PURE TEXT QUERY - return more text results
            final_results.extend(text_candidates[:20])
            
        else:
            # HYBRID QUERY - balanced mix
            final_results.extend(text_candidates[:12])
            final_results.extend(image_candidates[:8])
            final_results.sort(key=lambda x: x[1])
        
        format_start = time.time()
        all_results = [(doc.page_content, doc.metadata.get('source', 'unknown')) for doc, score in final_results]
        logger.info(f"⏱️ SEARCH: Format results took {time.time() - format_start:.3f}s")
        logger.info(f"⏱️ SEARCH: TOTAL search took {time.time() - vector_start:.3f}s with {len(all_results)} results, best_score={final_results[0][1] if final_results else 'N/A'}")
        logger.info(f"Intent: wants_images={wants_images}, wants_text={wants_text} | Candidates: text={len(text_candidates)}, images={len(image_candidates)} | Final: {len(final_results)}")
        
        # Log first 3 results for debugging
        if final_results:
            for i, (doc, score) in enumerate(final_results[:3]):
                content_preview = doc.page_content[:100].replace('\n', ' ')
                doc_type = doc.metadata.get('type', 'text')
                logger.info(f"Result {i+1}: score={score:.3f}, type={doc_type}, content={content_preview}...")
        
        if not all_results:
            result = "No relevant information found."
        else:
            # [OLD BUGGY CODE REMOVED]
            # if has_images:
            #    ... only returned IMAGE_URLs ...
            # else:
            #    ... returned text ...
            
            # [NEW FIXED CODE] Always return full content so the Agent can see both text AND image links
            result_parts = []
            for content, source in all_results:
                # Ensure we don't accidentally break the format the agent expects
                clean_content = content.strip()
                result_parts.append(f"[{source}] {clean_content}")
                
            result = "\n\n".join(result_parts) if result_parts else "No relevant information found."
        
        logger.info(f"⏱️ SEARCH: Search returned {len(all_results)} results, result length: {len(result)}")
        logger.info(f"⏱️ SEARCH: TOTAL handle_search_action took {time.time() - search_start:.3f}s")
        logger.info(f"✅ SEARCH COMPLETE - Returning {len(all_results)} results to agent")
        
        return {
            "messageVersion": "1.0",
            "response": {
                "actionGroup": event.get("actionGroup", "LambdaTools"),
                "apiPath": "/search",
                "httpMethod": "POST",
                "httpStatusCode": 200,
                "responseBody": {
                    "application/json": {
                        "body": json.dumps({"result": result})
                    }
                }
            }
        }
    except Exception as e:
        import traceback
        error_msg = str(e)
        stack_trace = traceback.format_exc()
        logger.error(f"Search failed: {type(e).__name__} | Details: {error_msg[:200]}")
        logger.error(f"Stack trace: {stack_trace[:500]}")
        
        # Return a generic success response with error details for debugging
        result_msg = f"Search completed but encountered an issue. Please try rephrasing your question."
        
        return {
            "messageVersion": "1.0",
            "response": {
                "actionGroup": event.get("actionGroup", "LambdaTools"),
                "apiPath": "/search",
                "httpMethod": "POST",
                "httpStatusCode": 200,
                "responseBody": {
                    "application/json": {
                        "body": json.dumps({"result": result_msg})
                    }
                }
            }
        }

def handle_send_email_action(event):
    """Send email via SES - called by Bedrock Agent."""
    try:
        request_body = event.get("requestBody", {})
        content = request_body.get("content", {})
        app_json = content.get("application/json", {})
        properties = app_json.get("properties", [])
        
        to_email = ""
        subject = ""
        body = ""
        
        for prop in properties:
            name = prop.get("name", "")
            value = prop.get("value", "")
            if name == "to_email":
                to_email = value
            elif name == "subject":
                subject = value
            elif name == "body":
                body = value
        
        logger.info(f"Sending email to: {sanitize_for_logging(to_email)}")
        
        if not to_email or not subject or not body:
            return {
                "messageVersion": "1.0",
                "response": {
                    "actionGroup": event.get("actionGroup", "LambdaTools"),
                    "apiPath": "/send-email",
                    "httpMethod": "POST",
                    "httpStatusCode": 400,
                    "responseBody": {
                        "application/json": {
                            "body": json.dumps({"error": "Missing required fields: to_email, subject, body"})
                        }
                    }
                }
            }
        
        # Send email via SES
        region = os.getenv("AWS_REGION")
        if not region:
            raise ValueError("AWS_REGION must be configured")
        
        sender_email = os.getenv("SES_SENDER_EMAIL")
        if not sender_email:
            raise ValueError("SES_SENDER_EMAIL must be configured")
        
        ses = boto3.client('ses', region_name=region)
        
        response = ses.send_email(
            Source=sender_email,
            Destination={'ToAddresses': [to_email]},
            Message={
                'Subject': {'Data': subject, 'Charset': 'UTF-8'},
                'Body': {'Text': {'Data': body, 'Charset': 'UTF-8'}}
            }
        )
        
        logger.info(f" Email sent successfully. MessageId: {response['MessageId']}")
        
        return {
            "messageVersion": "1.0",
            "response": {
                "actionGroup": event.get("actionGroup", "LambdaTools"),
                "apiPath": "/send-email",
                "httpMethod": "POST",
                "httpStatusCode": 200,
                "responseBody": {
                    "application/json": {
                        "body": json.dumps({"result": f"Email sent successfully to {to_email}"})
                    }
                }
            }
        }
    
    except Exception as e:
        logger.error(f"Email send failed: {sanitize_for_logging(str(e))}")
        return {
            "messageVersion": "1.0",
            "response": {
                "actionGroup": event.get("actionGroup", "LambdaTools"),
                "apiPath": "/send-email",
                "httpMethod": "POST",
                "httpStatusCode": 500,
                "responseBody": {
                    "application/json": {
                        "body": json.dumps({"error": "Email sending failed"})
                    }
                }
            }
        }





def handle_agent_query(event):
    """Route query to Bedrock Agent for natural language response."""
    total_start = time.time()
    try:
        parse_start = time.time()
        body_str = event.get("body", "{}")
        try:
            body = json.loads(body_str) if body_str else {}
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON | Error: {type(e).__name__} | Details: {str(e)[:100]}")
            return cors_response({"error": "Invalid JSON in request body"}, 400)
        
        query = body.get("query", "")
        session_id = body.get("sessionId", f"session-{int(time.time())}")
        logger.info(f"⏱️ TIMING: Parse body took {time.time() - parse_start:.3f}s")
        
        # Validate inputs
        if not query or not isinstance(query, str):
            return cors_response({"error": "Query is required and must be a string"}, 400)
        
        if len(query) > 10000:
            return cors_response({"error": "Query too long (max 10000 characters)"}, 400)
        
        config_start = time.time()
        agent_id = os.getenv("BEDROCK_AGENT_ID")
        alias_id = os.getenv("BEDROCK_AGENT_ALIAS_ID")
        
        if not agent_id or not alias_id:
            logger.error("BEDROCK_AGENT_ID or BEDROCK_AGENT_ALIAS_ID environment variable not set")
            return cors_response({"error": "Agent configuration error"}, 500)
        
        try:
            bedrock_agent_runtime = get_bedrock_client()
            logger.info(f"⏱️ TIMING: Get Bedrock client took {time.time() - config_start:.3f}s")
        except Exception as e:
            logger.error(f"Failed to get Bedrock client: {sanitize_for_logging(str(e))}")
            return cors_response({"error": "Failed to initialize agent client"}, 500)
        
        try:
            import signal
            
            def timeout_handler(signum, frame):
                raise TimeoutError("Agent invocation timed out")
            
            # Set 60 second timeout for agent invocation
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(60)
            
            invoke_start = time.time()
            logger.info(f"⏱️ TIMING: Starting agent invocation at {invoke_start - total_start:.3f}s")
            logger.info(f"🤖 AGENT QUERY: {sanitize_for_logging(query)}")
            logger.info(f"📋 Agent ID: {agent_id[:20]}... | Alias: {alias_id[:20]}...")
            try:
                response = bedrock_agent_runtime.invoke_agent(
                    agentId=agent_id,
                    agentAliasId=alias_id,
                    sessionId=session_id,
                    inputText=query,
                    enableTrace=True  # Enable trace to see if search is called
                )
                logger.info(f"⏱️ TIMING: Agent invocation completed in {time.time() - invoke_start:.3f}s")
            finally:
                signal.alarm(0)  # Cancel the alarm
                
        except TimeoutError as e:
            logger.error(f"Agent invocation timeout after {time.time() - invoke_start:.3f}s: {sanitize_for_logging(str(e))}")
            return cors_response({"error": "Request timed out. Please try a simpler query."}, 504)
        except Exception as e:
            logger.error(f"Agent invocation failed after {time.time() - invoke_start:.3f}s: {sanitize_for_logging(str(e))}")
            return cors_response({"error": "Failed to invoke agent"}, 500)
        
        stream_start = time.time()
        answer = ""
        chunk_count = 0
        trace_info = []
        try:
            event_stream = response.get('completion')
            if not event_stream:
                return cors_response({"error": "Invalid agent response"}, 500)
            
            for event in event_stream:
                # Log trace events to see if search is being called
                if 'trace' in event:
                    trace = event['trace']
                    if 'orchestrationTrace' in trace:
                        orch = trace['orchestrationTrace']
                        if 'invocationInput' in orch:
                            logger.info(f"🔍 Agent is invoking action: {json.dumps(orch['invocationInput'])[:200]}")
                        if 'observation' in orch:
                            logger.info(f"📊 Agent received observation: {json.dumps(orch['observation'])[:200]}")
                
                if 'chunk' in event and 'bytes' in event['chunk']:
                    answer += event['chunk']['bytes'].decode('utf-8')
                    chunk_count += 1
            logger.info(f"⏱️ TIMING: Stream processing took {time.time() - stream_start:.3f}s ({chunk_count} chunks, {len(answer)} bytes)")
        except Exception as e:
            full_error = str(e)
            logger.error(f"Failed to process response stream: {full_error}")
            return cors_response({"error": "Failed to process agent response"}, 500)
        
        # Extract IMAGE_URL: markers and generate presigned URLs
        image_start = time.time()
        images = []
        import re
        
        # [OLD CODE REMOVED] Matches strictly formatted IMAGE_URL tags
        # matches = re.findall(r'IMAGE_URL:([^|\n]+)', answer)

        # [NEW CODE] Robust regex to find any S3 image key pattern in the text
        # recognized formats: images/folder/file.jpeg, images/file.png, etc.
        image_path_pattern = r'(images/[\w\-\./]+?\.(?:jpeg|jpg|png))'
        matches = re.findall(image_path_pattern, answer, re.IGNORECASE)
        
        if matches:
            logger.info(f"Found {len(matches)} potential images in agent response")
            s3_client = get_s3_client()
            unique_keys = set()
            
            for s3_key in matches:
                s3_key = s3_key.strip()
                # Verify it's a valid image key and not a duplicate
                if s3_key and s3_key not in unique_keys:
                    unique_keys.add(s3_key)
                    try:
                        url = s3_client.generate_presigned_url(
                            'get_object',
                            Params={'Bucket': BUCKET, 'Key': s3_key},
                            ExpiresIn=300
                        )
                        images.append(url)
                        logger.info(f"Generated presigned URL for: {s3_key}")
                    except Exception as e:
                        logger.error(f"Failed to generate URL for {s3_key}: {e}")
            
            # [UPDATED CLEANUP LOGIC]
            if images:
                # 1. Split into lines
                lines = answer.split('\n')
                clean_lines = []
                for line in lines:
                    # Skip lines that contain the raw image keys we just processed
                    if any(key in line for key in unique_keys):
                        continue
                    
                    # Skip lines that are just filler conversational text
                    line_lower = line.strip().lower()
                    filler_phrases = [
                        'here are the images',
                        'i will display these images',
                        'the search results contain',
                        'found the following images',
                        'images for',
                        'image urls for',
                        '[system]',
                    ]
                    if any(phrase in line_lower for phrase in filler_phrases):
                        continue
                        
                    # If it passed checks, keep the line
                    if line.strip():
                         clean_lines.append(line)
                
                answer = '\n'.join(clean_lines).strip()
                
                # FINAL SAFETY CHECK: If we wiped everything out but found images, 
                # return a standard message so the UI has something to show.
                if not answer and images:
                    answer = "Here are the images you asked for:"
            
            # Final polish to remove stale newlines
            answer = re.sub(r'\n{3,}', '\n\n', answer)
            
        logger.info(f"⏱️ TIMING: Image URL generation took {time.time() - image_start:.3f}s ({len(images)} images)")
        
        logger.info(f"⏱️ TIMING: TOTAL agent query took {time.time() - total_start:.3f}s")
        return cors_response({"response": answer, "sessionId": session_id, "images": images})
    
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error | Error: {type(e).__name__} | Details: {str(e)[:100]}")
        return cors_response({"error": "Invalid request format"}, 400)
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Agent query failed | Error: {type(e).__name__} | Details: {error_msg[:200]} | Time: {time.time() - total_start:.2f}s")
        
        # Check if error is related to missing index
        if "index" in error_msg.lower() or "faiss" in error_msg.lower() or "vector" in error_msg.lower():
            return cors_response({"error": "No documents available. Please upload PDF files first to start asking questions."}, 200)
        
        return cors_response({"error": "Failed to process query. Please try again."}, 500)



def handle_get_image(event):
    """Generate presigned URL for image retrieval."""
    try:
        params = event.get("queryStringParameters") or {}
        image_key = params.get("key")
        
        logger.info(f"Get image request for key: {sanitize_for_logging(image_key)}")
        
        if not image_key or not isinstance(image_key, str):
            return cors_response({"error": "Missing or invalid image key"}, 400)
        
        # Validate key starts with images/ to prevent unauthorized access
        if not image_key.startswith("images/"):
            logger.warning(f"Attempted access to non-image key: {sanitize_for_logging(image_key)}")
            return cors_response({"error": "Invalid image key"}, 403)
        
        s3_client = get_s3_client()
        try:
            s3_client.head_object(Bucket=BUCKET, Key=image_key)
            logger.info(f"Image exists: {image_key}")
        except s3_client.exceptions.NoSuchKey:
            logger.error(f"Image not found: {image_key}")
            return cors_response({"error": "Image not found"}, 404)
        except Exception as e:
            logger.error(f"Failed to check image: {type(e).__name__}")
            return cors_response({"error": "Failed to verify image"}, 500)
        
        try:
            url = s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": BUCKET, "Key": image_key},
                ExpiresIn=300
            )
            logger.info(f"Generated presigned URL: {image_key}")
            return cors_response({"url": url})
        except Exception as e:
            logger.error(f"Failed to generate URL: {type(e).__name__}")
            return cors_response({"error": "Failed to generate image URL"}, 500)
            
    except Exception as e:
        logger.error(f"Get image error: {sanitize_for_logging(str(e))}")
        return cors_response({"error": "Failed to get image"}, 500)

def handle_processing_status(event):
    """Check processing status of uploaded file."""
    try:
        params = event.get("queryStringParameters") or {}
        file_name = params.get("fileName")
        
        try:
            file_name = validate_filename(file_name)
        except (ValueError, TypeError) as e:
            return cors_response({"error": "Invalid fileName"}, 400)
        
        base_name = os.path.splitext(file_name)[0] if '.' in file_name else file_name
        logger.info(f" Checking status for file: {sanitize_for_logging(file_name)}")
        
        s3_client = get_s3_client()
        
        # Check if cancelled
        try:
            s3_client.head_object(Bucket=BUCKET, Key=f"cancelled/{base_name}.txt")
            return cors_response({
                "status": "cancelled",
                "progress": 0,
                "message": "Processing was cancelled"
            })
        except s3_client.exceptions.NoSuchKey:
            pass
        except Exception as e:
            logger.error(f"Error checking cancellation: {type(e).__name__}")
        
        # Check if processing is complete
        try:
            logger.info(f"Checking: s3://{BUCKET}/processed/{base_name}.json")
            processed_obj = s3_client.get_object(Bucket=BUCKET, Key=f"processed/{base_name}.json")
            processed_data = json.loads(processed_obj['Body'].read().decode('utf-8'))
            logger.info(f"Found completion marker: {base_name}")
            return cors_response({
                "status": "completed",
                "progress": 100,
                "message": "Processing complete",
                "data": processed_data
            })
        except s3_client.exceptions.NoSuchKey:
            logger.info(f"Processed marker not found")
        except Exception as e:
            logger.error(f"Error checking processed: {type(e).__name__}")
        
        # Check for progress updates from Lambda
        try:
            progress_obj = s3_client.get_object(Bucket=BUCKET, Key=f"progress/{base_name}.json")
            progress_data = json.loads(progress_obj['Body'].read().decode('utf-8'))
            logger.info(f"Found progress marker: {progress_data}")
            return cors_response({
                "status": progress_data.get("status", "processing"),
                "progress": progress_data.get("progress", 50),
                "message": progress_data.get("message", "Processing...")
            })
        except s3_client.exceptions.NoSuchKey:
            logger.info(f"Progress marker not found")
        except Exception as e:
            logger.error(f"Error checking progress: {type(e).__name__}")
        
        # Check if file exists in uploads (fallback)
        try:
            s3_client.head_object(Bucket=BUCKET, Key=f"uploads/{file_name}")
            logger.info(f"File in uploads, processing")
            return cors_response({
                "status": "processing",
                "progress": 50,
                "message": "Processing document..."
            })
        except s3_client.exceptions.NoSuchKey:
            pass
        except Exception as e:
            logger.error(f"Error checking uploads: {type(e).__name__}")
        
        # File not found anywhere
        return cors_response({
            "status": "not_found",
            "progress": 0,
            "message": "File not found or processing not started"
        })
        
    except Exception as e:
        logger.error(f" Processing status error: {type(e).__name__}")
        return cors_response({"error": "Failed to check processing status"}, 500)


# -----------------------------------------------------------
# Lambda Entrypoint
# -----------------------------------------------------------
def lambda_handler(event, context):
    """Main Lambda handler for API Gateway and Bedrock Agent requests."""
    # Set correlation ID for request tracking
    request_id = context.request_id if hasattr(context, 'request_id') else str(uuid.uuid4())
    correlation_id_var.set(request_id)
    
    logger.info(f"Lambda triggered | RequestId: {request_id} | Event: {json.dumps(event)[:500]}")
    
    # Handle warmup ping from EventBridge
    if event.get("source") == "aws.events" and event.get("detail-type") == "Scheduled Event":
        logger.info("Warmup ping received")
        return {"statusCode": 200, "body": json.dumps({"status": "warm"})}
    
    # Check if this is a Bedrock Agent action invocation
    if "messageVersion" in event and "agent" in event:
        api_path = event.get("apiPath", "")
        logger.info(f"Bedrock Agent action | Path: {api_path}")
        if api_path == "/search":
            return handle_search_action(event)
        elif api_path == "/send-email":
            return handle_send_email_action(event)
        else:
            return {
                "messageVersion": "1.0",
                "response": {
                    "actionGroup": event.get("actionGroup", ""),
                    "apiPath": api_path,
                    "httpMethod": event.get("httpMethod", "POST"),
                    "httpStatusCode": 404,
                    "responseBody": {
                        "application/json": {
                            "body": json.dumps({"error": "Unknown action"})
                        }
                    }
                }
            }
    
    # API Gateway invocations
    path = event.get("path", "")
    method = event.get("httpMethod", "")
    logger.info(f"API Gateway request | Method: {method} | Path: {path}")

    if path.startswith("/production/"):
        path = "/" + path[12:]
    elif path.startswith("/default/"):
        path = "/" + path[8:]
    elif path.startswith("/prod/"):
        path = "/" + path[5:]
    
    if path != event.get("path", ""):
        logger.info(f"Path normalized | Original: {event.get('path')} | Cleaned: {path}")

    if method == "OPTIONS":
        return cors_response()

    try:
        if path == "/upload" and method == "POST":
            return handle_get_upload_url_api(event)
        elif path == "/get-upload-url" and method in ["GET", "POST"]:
            return handle_get_upload_url_api(event)
        elif path == "/list-files" and method == "GET":
            return handle_list_files_api(event)
        elif path == "/delete-file" and method in ["DELETE", "GET"]:
            return handle_delete_file_api(event)
        elif path == "/cancel-upload" and method == "DELETE":
            return handle_cancel_upload_api(event)
        elif path == "/agent-query" and method == "POST":
            return handle_agent_query(event)
        elif path == "/get-image" and method == "GET":
            return handle_get_image(event)
        elif path == "/processing-status" and method == "GET":
            return handle_processing_status(event)
        else:
            logger.error(f"Unhandled route | Path: {path} | Method: {method}")
            return cors_response({"error": f"Unhandled route: {path}"}, 404)

    except Exception as e:
        logger.error(f"Lambda error | Type: {type(e).__name__} | Message: {str(e)[:200]}")
        return cors_response({"error": "Internal server error"}, 500)
