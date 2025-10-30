import json
import boto3
import logging
import os
import time
from urllib.parse import unquote_plus

# -----------------------------------------------------------
# Logging
# -----------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# -----------------------------------------------------------
# AWS Setup
# -----------------------------------------------------------
from botocore.client import Config
s3 = boto3.client("s3", config=Config(signature_version='s3v4'))
BUCKET = os.getenv("S3_BUCKET")
if not BUCKET:
    raise ValueError("S3_BUCKET environment variable must be set")

# Cache for FAISS indexes in /tmp
FAISS_CACHE = {}

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
        url = s3.generate_presigned_url(
            "put_object",
            Params={"Bucket": BUCKET, "Key": key, "ContentType": "application/pdf"},
            ExpiresIn=3600,
        )
        logger.info(f" Generated upload URL for {key}")
        return cors_response({"uploadUrl": url, "key": key})
    except Exception as e:
        logger.error(f" Failed to generate upload URL: {type(e).__name__}")
        return cors_response({"error": "Failed to generate upload URL"}, 500)


# -----------------------------------------------------------
# /list-files
# -----------------------------------------------------------
def handle_list_files():
    """List processed PDFs available for querying."""
    try:
        logger.info(" Listing processed PDFs...")
        response = s3.list_objects_v2(Bucket=BUCKET, Prefix="processed/")
        files = []
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
        body = json.loads(body_str) if body_str else {}
        file_name = body.get("fileName", f"upload_{int(time.time())}.pdf")
        base_name = os.path.splitext(file_name)[0] if '.' in file_name else file_name
        
        key = f"uploads/{file_name}"
        signed_url = s3.generate_presigned_url(
            "put_object",
            Params={"Bucket": BUCKET, "Key": key, "ContentType": "application/pdf"},
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
        response = s3.list_objects_v2(Bucket=BUCKET, Prefix="processed/")
        filenames = []
        for obj in response.get("Contents", []):
            if obj["Key"].endswith(".json"):
                filenames.append(os.path.basename(obj["Key"]))
        return cors_response({"filenames": filenames})
    except Exception as e:
        logger.error(f" List files error: {type(e).__name__}")
        return cors_response({"error": "Failed to list files"}, 500)

def handle_delete_file_api(event):
    """API Gateway handler for deleting files."""
    try:
        params = event.get("queryStringParameters") or {}
        display_name = params.get("fileName")
        if not display_name:
            return cors_response({"error": "Missing fileName"}, 400)
        
        logger.info(f" Deleting file: {display_name}")
        
        base_name = display_name.replace('.json', '') if display_name.endswith('.json') else display_name
        
        # Delete JSON marker
        try:
            s3.delete_object(Bucket=BUCKET, Key=f"processed/{base_name}.json")
            logger.info(f" Deleted JSON marker")
        except Exception as e:
            logger.error(f" Failed to delete JSON marker: {e}")
        
        # Delete original PDF
        try:
            response = s3.list_objects_v2(Bucket=BUCKET, Prefix=f"uploads/{base_name}")
            for obj in response.get('Contents', []):
                if obj['Key'].startswith(f"uploads/{base_name}."):
                    s3.delete_object(Bucket=BUCKET, Key=obj['Key'])
                    logger.info(f" Deleted PDF: {obj['Key']}")
        except Exception as e:
            logger.error(f" Failed to delete PDF: {e}")
        
        # Delete images
        try:
            response = s3.list_objects_v2(Bucket=BUCKET, Prefix=f"images/{base_name}/")
            for obj in response.get('Contents', []):
                s3.delete_object(Bucket=BUCKET, Key=obj['Key'])
                logger.info(f" Deleted image: {obj['Key']}")
        except Exception as e:
            logger.error(f" Failed to delete images: {e}")
        
        # Delete vector store
        try:
            response = s3.list_objects_v2(Bucket=BUCKET, Prefix=f"vector_store/{base_name}/")
            for obj in response.get('Contents', []):
                s3.delete_object(Bucket=BUCKET, Key=obj['Key'])
                logger.info(f" Deleted vector: {obj['Key']}")
        except Exception as e:
            logger.error(f" Failed to delete vectors: {e}")
        
        return cors_response({"message": f"{base_name} deleted successfully"})
    except Exception as e:
        logger.error(f" Delete file error: {type(e).__name__}")
        return cors_response({"error": "Failed to delete file"}, 500)

def handle_cancel_upload_api(event):
    """API Gateway handler for cancelling uploads and cleaning up partial files."""
    try:
        params = event.get("queryStringParameters") or {}
        file_name = params.get("fileName")
        if not file_name:
            return cors_response({"error": "Missing fileName"}, 400)
        
        logger.info(f" Cancelling upload: {file_name}")
        base_name = os.path.splitext(file_name)[0] if '.' in file_name else file_name
        deleted_count = 0
        
        # Create cancellation marker FIRST to stop Lambda processing
        try:
            s3.put_object(
                Bucket=BUCKET,
                Key=f"cancelled/{base_name}.txt",
                Body=f"Cancelled at {time.time()}",
                ContentType="text/plain"
            )
            logger.info(f" Created cancellation marker")
        except Exception as e:
            logger.error(f" Failed to create cancellation marker: {e}")
        
        # Delete ALL files matching base_name in uploads/
        try:
            response = s3.list_objects_v2(Bucket=BUCKET, Prefix=f"uploads/{base_name}")
            for obj in response.get('Contents', []):
                s3.delete_object(Bucket=BUCKET, Key=obj['Key'])
                deleted_count += 1
                logger.info(f" Deleted: {obj['Key']}")
        except Exception as e:
            logger.error(f" Failed to delete uploads: {e}")
        
        # Delete ALL files matching base_name in processed/
        try:
            response = s3.list_objects_v2(Bucket=BUCKET, Prefix=f"processed/{base_name}")
            for obj in response.get('Contents', []):
                s3.delete_object(Bucket=BUCKET, Key=obj['Key'])
                deleted_count += 1
                logger.info(f" Deleted: {obj['Key']}")
        except Exception as e:
            logger.error(f" Failed to delete processed: {e}")
        
        # Delete ALL files in images/{base_name}/
        try:
            response = s3.list_objects_v2(Bucket=BUCKET, Prefix=f"images/{base_name}/")
            for obj in response.get('Contents', []):
                s3.delete_object(Bucket=BUCKET, Key=obj['Key'])
                deleted_count += 1
                logger.info(f" Deleted: {obj['Key']}")
        except Exception as e:
            logger.error(f" Failed to delete images: {e}")
        
        # Delete ALL files in vector_store/{base_name}/
        try:
            response = s3.list_objects_v2(Bucket=BUCKET, Prefix=f"vector_store/{base_name}/")
            for obj in response.get('Contents', []):
                s3.delete_object(Bucket=BUCKET, Key=obj['Key'])
                deleted_count += 1
                logger.info(f" Deleted: {obj['Key']}")
        except Exception as e:
            logger.error(f" Failed to delete vectors: {e}")
        
        # Delete the cancellation marker itself
        try:
            s3.delete_object(Bucket=BUCKET, Key=f"cancelled/{base_name}.txt")
            logger.info(f" Deleted cancellation marker")
        except Exception as e:
            logger.error(f" Failed to delete cancellation marker: {e}")
        
        logger.info(f" Total files deleted: {deleted_count}")
        return cors_response({"message": f"Cancelled and deleted {deleted_count} files for {base_name}"})
    except Exception as e:
        logger.error(f" Cancel upload error: {type(e).__name__}")
        return cors_response({"error": "Failed to cancel upload"}, 500)

def get_agent_alias_id():
    """Lookup the agent alias ID by name at runtime."""
    agent_id = os.getenv("BEDROCK_AGENT_ID")
    alias_name = os.getenv("BEDROCK_AGENT_ALIAS_NAME", "production")
    
    bedrock_agent = boto3.client("bedrock-agent", region_name=os.getenv("AWS_REGION", "us-east-1"))
    response = bedrock_agent.list_agent_aliases(agentId=agent_id)
    
    for alias in response.get("agentAliasSummaries", []):
        if alias["agentAliasName"] == alias_name:
            return alias["agentAliasId"]
    
    raise ValueError(f"Agent alias '{alias_name}' not found")

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
        
        logger.info(f" Sending email to: {to_email}")
        
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
        ses = boto3.client('ses', region_name=os.getenv("AWS_REGION", "us-east-1"))
        sender_email = os.getenv("SES_SENDER_EMAIL", "noreply@example.com")
        
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
        logger.error(f" Email send failed: {type(e).__name__}")
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

def handle_search_action(event):
    """Search all FAISS indexes - called by Bedrock Agent."""
    from langchain_aws import BedrockEmbeddings
    from langchain_community.vectorstores import FAISS
    import tempfile
    
    try:
        request_body = event.get("requestBody", {})
        content = request_body.get("content", {})
        app_json = content.get("application/json", {})
        properties = app_json.get("properties", [])
        
        query = ""
        for prop in properties:
            if prop.get("name") == "query":
                query = prop.get("value", "")
                break
        
        logger.info(f" Agent searching for: '{query}'")
        logger.info(f" Query length: {len(query)} characters")
        
        # Expand search terms for better results
        expanded_queries = [query]
        if query and query.strip():  # Only expand if query is not empty
            query_lower = query.lower()
            
            # Add synonyms for common automotive terms
            if any(term in query_lower for term in ['engine', 'motor']):
                expanded_queries.extend([query + ' displacement', query + ' specifications', query + ' horsepower'])
            
            if 'size' in query_lower:
                expanded_queries.extend([query.replace('size', 'displacement'), query.replace('size', 'capacity')])
        
        logger.info(f" Expanded search terms: {expanded_queries[:3]}")  # Limit logging
        
        # Handle empty query
        if not query or not query.strip():
            response = s3.list_objects_v2(Bucket=BUCKET, Prefix="vector_store/", Delimiter="/")
            folders = [p.get("Prefix") for p in response.get("CommonPrefixes", [])]
            if folders:
                file_list = [f.replace("vector_store/", "").replace("/", "") for f in folders]
                result = f"I have access to the following documents: {', '.join(file_list)}"
            else:
                result = "No documents have been indexed yet."
        else:
            # List all vector store folders
            response = s3.list_objects_v2(Bucket=BUCKET, Prefix="vector_store/", Delimiter="/")
            folders = [p.get("Prefix") for p in response.get("CommonPrefixes", [])]
            
            if not folders:
                result = "No documents have been indexed yet."
            else:
                embeddings = BedrockEmbeddings(
                model_id="amazon.titan-embed-text-v1",
                region_name=os.getenv("AWS_REGION", "us-east-1")
            )
            
            all_docs = []
            for folder in folders:
                try:
                    # Use cached index if available
                    cache_key = folder
                    if cache_key in FAISS_CACHE:
                        logger.info(f" Using cached index for {folder}")
                        index = FAISS_CACHE[cache_key]
                    else:
                        # Download to /tmp for caching across invocations
                        cache_dir = f"/tmp/{folder.replace('/', '_')}"
                        os.makedirs(cache_dir, exist_ok=True)
                        
                        s3.download_file(BUCKET, f"{folder}index.faiss", os.path.join(cache_dir, "index.faiss"))
                        s3.download_file(BUCKET, f"{folder}index.pkl", os.path.join(cache_dir, "index.pkl"))
                        
                        index = FAISS.load_local(cache_dir, embeddings, allow_dangerous_deserialization=True)
                        FAISS_CACHE[cache_key] = index
                        logger.info(f" Cached index for {folder}")
                    
                    # Search with similarity scores
                    docs_with_scores = index.similarity_search_with_score(query, k=10)
                    all_docs.extend(docs_with_scores)
                    logger.info(f" Loaded {len(docs_with_scores)} docs from {folder}")
                except Exception as e:
                    logger.warning(f"Failed to load index from {folder}: {e}")
            
            if not all_docs:
                result = "No relevant documents found."
            else:
                # Sort by FAISS similarity score (lower is better)
                all_docs.sort(key=lambda x: x[1])
                
                # Take top 15 most similar
                all_docs = all_docs[:15]
                parts = []
                images = []
                
                logger.info(f" Processing {len(all_docs)} documents for query: {query}")
                
                for doc, faiss_score in all_docs:
                    source = doc.metadata.get('source', 'Unknown')
                    content = doc.page_content.strip()
                    doc_type = doc.metadata.get('type', 'text')
                    
                    if doc_type == 'image':
                        # Get the S3 key from metadata
                        s3_key = doc.metadata.get('s3_key', '')
                        if not s3_key:
                            # Fallback: construct from image_url
                            image_url = doc.metadata.get('image_url', '')
                            if image_url.startswith('https://'):
                                s3_key = image_url.split('.com/')[-1]
                            else:
                                s3_key = image_url
                        
                        page = doc.metadata.get('page', 'unknown')
                        description = doc.metadata.get('description', 'Image')
                        
                        logger.info(f"Found image (score={faiss_score}): {s3_key} - {description[:50]}...")
                        
                        images.append(f"IMAGE_URL:{s3_key}|PAGE:{page}|SOURCE:{source}|DESC:{description}")
                        parts.append(f"[{source} - Page {page}]: {content}")
                    else:
                        parts.append(f"[{source}]: {content}")
                
                result = "\n\n".join(parts)
                if images:
                    logger.info(f"Adding {len(images)} images to result")
                    result += "\n\nIMAGES:\n" + "\n".join(images)
                else:
                    logger.info("No images found in search results")
                    doc_types = [doc[0].metadata.get('type', 'text') for doc in all_docs]
                    logger.info(f"Doc types found: {doc_types}")
        
        logger.info(f" Search complete, found {len(all_docs) if 'all_docs' in locals() else 0} docs")
        logger.info(f" Folders found: {folders if 'folders' in locals() else 'None'}")
        logger.info(f" Bucket: {BUCKET}")
        logger.info(f" Final result length: {len(result) if 'result' in locals() else 0}")
        
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
        logger.error(f" Search failed: {type(e).__name__}")
        return {
            "messageVersion": "1.0",
            "response": {
                "actionGroup": event.get("actionGroup", "LambdaTools"),
                "apiPath": "/search",
                "httpMethod": "POST",
                "httpStatusCode": 500,
                "responseBody": {
                    "application/json": {
                        "body": json.dumps({"error": "Search operation failed"})
                    }
                }
            }
        }

def handle_agent_query(event):
    """Route query to Bedrock Agent for natural language response."""
    try:
        body = json.loads(event.get("body", "{}"))
        query = body.get("query", "")
        session_id = body.get("sessionId", f"session-{int(time.time())}")
        
        # Sanitize inputs for logging to prevent log injection
        safe_query = ''.join(c if c.isprintable() else ' ' for c in (query or 'None'))[:100]
        safe_session = ''.join(c if c.isprintable() else ' ' for c in (session_id or 'None'))[:50]
        logger.info(f" Query: {safe_query}")
        logger.info(f" Session: {safe_session}")

        agent_id = os.getenv("BEDROCK_AGENT_ID")
        logger.info(f" Agent ID: {agent_id}")
        
        try:
            alias_id = get_agent_alias_id()
            logger.info(f" Agent Alias ID: {alias_id}")
        except Exception as e:
            logger.error(f" Failed to get alias ID: {e}")
            # Fallback to environment variable
            alias_id = os.getenv("BEDROCK_AGENT_ALIAS_ID")
            logger.info(f" Using fallback alias ID: {alias_id}")
        
        bedrock_agent_runtime = boto3.client(
            "bedrock-agent-runtime",
            region_name=os.getenv("AWS_REGION", "us-east-1")
        )
        logger.info(f" Invoking agent with agentId={agent_id}, aliasId={alias_id}, sessionId={session_id}")
        
        response = bedrock_agent_runtime.invoke_agent(
            agentId=agent_id,
            agentAliasId=alias_id,
            sessionId=session_id,
            inputText=query,
            enableTrace=False
        )
        logger.info(f" Agent invoked successfully, processing response stream")
        
        answer = ""
        event_stream = response['completion']
        for event in event_stream:
            if 'chunk' in event:
                chunk = event['chunk']
                if 'bytes' in chunk:
                    answer += chunk['bytes'].decode('utf-8')
        
        # Extract images from agent's search results
        images = []
        query_lower = query.lower()
        
        # Check if query asks for images or visual content
        image_keywords = ['show', 'display', 'see', 'view', 'look', 'find', 'get', 'image', 'picture', 'photo']
        wants_images = any(keyword in query_lower for keyword in image_keywords)
        
        if wants_images:
            logger.info(f" Image query detected")
            try:
                # Parse IMAGE_URL markers from answer
                import re
                image_pattern = r'IMAGE_URL:([^|]+)\|PAGE:([^|]+)\|SOURCE:([^|]+)(?:\|DESC:([^\n]+))?'
                matches = re.findall(image_pattern, answer)
                
                if matches:
                    logger.info(f" Processing {len(matches)} images from search results")
                    
                    for i, match in enumerate(matches):
                        image_url = match[0].strip()
                        description = match[3] if len(match) > 3 else 'No description'
                        logger.info(f" Image {i+1}: {image_url} - {description}")
                        
                        # Generate presigned URL from S3 key
                        if image_url.startswith('https://'):
                            s3_key = image_url.split('.com/')[-1]
                        else:
                            s3_key = image_url
                        
                        try:
                            url = s3.generate_presigned_url(
                                'get_object',
                                Params={'Bucket': BUCKET, 'Key': s3_key},
                                ExpiresIn=3600
                            )
                            images.append(url)
                            logger.info(f" Generated URL for image {i+1}")
                        except Exception as e:
                            logger.error(f" Failed to generate URL for {s3_key}: {e}")
                    
                    logger.info(f" Returning {len(images)} image URLs")
            except Exception as e:
                logger.error(f" Image extraction failed: {e}")
        
        logger.info(f" Agent response: {answer[:100]}...")
        logger.info(f" Returning {len(images)} processed image URLs")
        return cors_response({"response": answer, "sessionId": session_id, "images": images})
    
    except Exception as e:
        logger.error(f" Agent query failed: {type(e).__name__}")
        logger.error(f" Error details: {str(e)}")
        import traceback
        logger.error(f" Traceback: {traceback.format_exc()}")
        return cors_response({"error": "Agent query failed"}, 500)

def handle_get_image(event):
    """Generate presigned URL for image retrieval."""
    try:
        params = event.get("queryStringParameters") or {}
        image_key = params.get("key")
        
        if not image_key:
            return cors_response({"error": "Missing image key"}, 400)
        
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": BUCKET, "Key": image_key},
            ExpiresIn=3600
        )
        
        return cors_response({"url": url})
    except Exception as e:
        logger.error(f" Get image error: {type(e).__name__}")
        return cors_response({"error": "Failed to get image"}, 500)

def handle_processing_status(event):
    """Check processing status of uploaded file."""
    try:
        params = event.get("queryStringParameters") or {}
        file_name = params.get("fileName")
        
        if not file_name:
            logger.error(" Missing fileName parameter")
            return cors_response({"error": "Missing fileName"}, 400)
        
        base_name = os.path.splitext(file_name)[0] if '.' in file_name else file_name
        logger.info(f" Checking status for file: {file_name}, base_name: {base_name}")
        logger.info(f" Will check for: processed/{base_name}.json")
        
        # Check if cancelled - don't delete marker, just report status
        try:
            s3.head_object(Bucket=BUCKET, Key=f"cancelled/{base_name}.txt")
            return cors_response({
                "status": "cancelled",
                "progress": 0,
                "message": "Processing was cancelled"
            })
        except s3.exceptions.NoSuchKey:
            pass  # Not cancelled, continue checking
        except Exception as e:
            logger.error(f"Error checking cancellation: {e}")
            pass  # Continue checking other statuses
        
        # Check if processing is complete - look for processed marker
        try:
            logger.info(f" Attempting to get: s3://{BUCKET}/processed/{base_name}.json")
            processed_obj = s3.get_object(Bucket=BUCKET, Key=f"processed/{base_name}.json")
            processed_data = json.loads(processed_obj['Body'].read().decode('utf-8'))
            logger.info(f" Found completion marker for {base_name}")
            return cors_response({
                "status": "completed",
                "progress": 100,
                "message": "Processing complete",
                "data": processed_data
            })
        except s3.exceptions.NoSuchKey:
            logger.info(f" Processed marker not found")
            pass  # Not processed yet, continue checking
        except Exception as e:
            logger.error(f"Error checking processed status: {e}")
            pass  # Continue checking other statuses
        
        # Check if file exists in uploads (still processing)
        try:
            s3.head_object(Bucket=BUCKET, Key=f"uploads/{file_name}")
            logger.info(f" File in uploads, processing in progress")
            return cors_response({
                "status": "processing",
                "progress": 75,
                "message": "Extracting text and creating vector embeddings..."
            })
        except s3.exceptions.NoSuchKey:
            pass  # Not in uploads, file not found
        except Exception as e:
            logger.error(f"Error checking uploads: {e}")
        
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
    logger.info(f" Lambda triggered: {json.dumps(event)[:500]}")
    
    # Handle warmup ping from EventBridge
    if event.get("source") == "aws.events" and event.get("detail-type") == "Scheduled Event":
        logger.info(" Warmup ping received, keeping Lambda warm")
        return {"statusCode": 200, "body": json.dumps({"status": "warm"})}
    
    # Check if this is a Bedrock Agent action invocation
    if "messageVersion" in event and "agent" in event:
        logger.info(" Bedrock Agent action invocation detected")
        api_path = event.get("apiPath", "")
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
    logger.info(f" Raw path: {path} | Method: {method}")

    if path.startswith("/production/"):
        path = "/" + path[12:]
    elif path.startswith("/default/"):
        path = "/" + path[8:]
    elif path.startswith("/prod/"):
        path = "/" + path[5:]
    
    logger.info(f"Cleaned path: {path}")

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
            logger.error(f"Unhandled route: {path}")
            return cors_response({"error": f"Unhandled route: {path}"}, 404)

    except Exception as e:
        logger.error(f"Lambda error: {type(e).__name__}")
        return cors_response({"error": "Internal server error"}, 500)
