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
s3 = boto3.client("s3")
BUCKET = os.getenv("S3_BUCKET", os.getenv("DOCUMENTS_BUCKET", "pdfquery-rag-documents-default"))

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
        logger.info(f"🆙 Generated upload URL for {key}")
        return cors_response({"uploadUrl": url, "key": key})
    except Exception as e:
        logger.error(f"❌ Failed to generate upload URL: {e}")
        return cors_response({"error": str(e)}, 500)


# -----------------------------------------------------------
# /list-files
# -----------------------------------------------------------
def handle_list_files():
    """List processed PDFs available for querying."""
    try:
        logger.info("📁 Listing processed PDFs...")
        response = s3.list_objects_v2(Bucket=BUCKET, Prefix="processed/")
        files = []
        for item in response.get("Contents", []):
            key = item["Key"]
            if key.lower().endswith(".pdf"):
                files.append(os.path.basename(key))
        logger.info(f"📁 Listed {len(files)} processed PDFs.")
        return cors_response({"files": files})
    except Exception as e:
        logger.error(f"❌ Failed to list files: {e}")
        return cors_response({"error": str(e)}, 500)


# -----------------------------------------------------------
# /agent-query
# -----------------------------------------------------------
def handle_get_upload_url_api(event):
    """API Gateway handler for generating upload URLs."""
    try:
        # Handle both GET (query params) and POST (body) requests
        if event.get("httpMethod") == "POST":
            body = json.loads(event.get("body", "{}"))
            logger.info(f"📝 POST body: {body}")
            file_name = body.get("fileName")
            file_type = body.get("fileType", "application/pdf")
        else:
            params = event.get("queryStringParameters") or {}
            logger.info(f"📝 GET params: {params}")
            file_name = params.get("fileName")
            file_type = params.get("fileType", "application/pdf")
        
        # If no fileName provided, generate one
        if not file_name:
            timestamp = int(time.time())
            file_name = f"upload_{timestamp}.pdf"
            logger.info(f"📝 Generated fileName: {file_name}")
        
        key = f"uploads/{file_name}"
        signed_url = s3.generate_presigned_url(
            "put_object",
            Params={"Bucket": BUCKET, "Key": key, "ContentType": file_type},
            ExpiresIn=3600,
        )
        logger.info(f"✅ Generated upload URL for key: {key}")
        return cors_response({"signedUrl": signed_url, "fileName": file_name})
    except Exception as e:
        logger.error(f"❌ Upload URL error: {e}")
        return cors_response({"error": str(e)}, 500)

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
        return cors_response({"error": str(e)}, 500)

def handle_delete_file_api(event):
    """API Gateway handler for deleting files."""
    try:
        params = event.get("queryStringParameters") or {}
        display_name = params.get("fileName")
        if not display_name:
            return cors_response({"error": "Missing fileName"}, 400)
        
        logger.info(f"🗑️ Deleting file: {display_name}")
        
        base_name = display_name.replace('.json', '') if display_name.endswith('.json') else display_name
        
        # Delete JSON marker
        try:
            s3.delete_object(Bucket=BUCKET, Key=f"processed/{base_name}.json")
            logger.info(f"✅ Deleted JSON marker")
        except Exception as e:
            logger.error(f"❌ Failed to delete JSON marker: {e}")
        
        # Delete original PDF
        try:
            response = s3.list_objects_v2(Bucket=BUCKET, Prefix=f"uploads/{base_name}")
            for obj in response.get('Contents', []):
                if obj['Key'].startswith(f"uploads/{base_name}."):
                    s3.delete_object(Bucket=BUCKET, Key=obj['Key'])
                    logger.info(f"✅ Deleted PDF: {obj['Key']}")
        except Exception as e:
            logger.error(f"❌ Failed to delete PDF: {e}")
        
        # Delete vector store
        try:
            response = s3.list_objects_v2(Bucket=BUCKET, Prefix=f"vector_store/{base_name}/")
            for obj in response.get('Contents', []):
                s3.delete_object(Bucket=BUCKET, Key=obj['Key'])
                logger.info(f"✅ Deleted vector: {obj['Key']}")
        except Exception as e:
            logger.error(f"❌ Failed to delete vectors: {e}")
        
        return cors_response({"message": f"{base_name} deleted successfully"})
    except Exception as e:
        logger.error(f"❌ Delete file error: {e}")
        return cors_response({"error": str(e)}, 500)

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
        
        logger.info(f"📧 Sending email to: {to_email}")
        
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
        
        logger.info(f"✅ Email sent successfully. MessageId: {response['MessageId']}")
        
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
        logger.error(f"❌ Email send failed: {e}")
        return {
            "messageVersion": "1.0",
            "response": {
                "actionGroup": event.get("actionGroup", "LambdaTools"),
                "apiPath": "/send-email",
                "httpMethod": "POST",
                "httpStatusCode": 500,
                "responseBody": {
                    "application/json": {
                        "body": json.dumps({"error": str(e)})
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
        
        logger.info(f"🔍 Agent searching for: {query}")
        
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
                    with tempfile.TemporaryDirectory() as tmpdir:
                        s3.download_file(BUCKET, f"{folder}index.faiss", os.path.join(tmpdir, "index.faiss"))
                        s3.download_file(BUCKET, f"{folder}index.pkl", os.path.join(tmpdir, "index.pkl"))
                        
                        index = FAISS.load_local(tmpdir, embeddings, allow_dangerous_deserialization=True)
                        docs = index.similarity_search(query, k=2)
                        all_docs.extend(docs)
                        logger.info(f"✅ Loaded {len(docs)} docs from {folder}")
                except Exception as e:
                    logger.warning(f"Failed to load index from {folder}: {e}")
            
            if not all_docs:
                result = "No relevant documents found."
            else:
                # Sort by relevance and take top 3
                all_docs = all_docs[:3]
                parts = []
                images = []
                
                for doc in all_docs:
                    source = doc.metadata.get('source', 'Unknown')
                    content = doc.page_content.strip()
                    
                    # Check if this is an image document
                    if doc.metadata.get('type') == 'image':
                        image_url = doc.metadata.get('image_url', '')
                        page = doc.metadata.get('page', 'unknown')
                        images.append(f"IMAGE_URL:{image_url}|PAGE:{page}|SOURCE:{source}")
                        parts.append(f"[{source} - Page {page}]: Contains an image")
                    else:
                        parts.append(f"[{source}]: {content}")
                
                result = "\n\n".join(parts)
                if images:
                    result += "\n\nIMAGES:\n" + "\n".join(images)
        
        logger.info(f"✅ Search complete, found {len(all_docs) if all_docs else 0} docs")
        logger.info(f"📂 Folders found: {folders}")
        logger.info(f"🪣 Bucket: {BUCKET}")
        
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
        logger.error(f"❌ Search failed: {e}")
        return {
            "messageVersion": "1.0",
            "response": {
                "actionGroup": event.get("actionGroup", "LambdaTools"),
                "apiPath": "/search",
                "httpMethod": "POST",
                "httpStatusCode": 500,
                "responseBody": {
                    "application/json": {
                        "body": json.dumps({"error": str(e)})
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
        
        logger.info(f"💬 Query: {query}")
        logger.info(f"🔑 Session: {session_id}")

        agent_id = os.getenv("BEDROCK_AGENT_ID")
        alias_id = get_agent_alias_id()
        
        bedrock_agent_runtime = boto3.client(
            "bedrock-agent-runtime",
            region_name=os.getenv("AWS_REGION", "us-east-1")
        )
        
        response = bedrock_agent_runtime.invoke_agent(
            agentId=agent_id,
            agentAliasId=alias_id,
            sessionId=session_id,
            inputText=query
        )
        
        answer = ""
        for event_chunk in response.get("completion", []):
            if "chunk" in event_chunk:
                chunk_data = event_chunk["chunk"]
                if "bytes" in chunk_data:
                    answer += chunk_data["bytes"].decode("utf-8")
        
        # Extract image URLs from response
        images = []
        if "IMAGES:" in answer:
            parts = answer.split("IMAGES:")
            answer_text = parts[0].strip()
            image_lines = parts[1].strip().split("\n")
            for line in image_lines:
                if line.startswith("IMAGE_URL:"):
                    img_parts = line.split("|")
                    img_url = img_parts[0].replace("IMAGE_URL:", "").strip()
                    images.append(img_url)
            answer = answer_text
        
        logger.info(f"✅ Agent response: {answer[:100]}...")
        logger.info(f"📸 Found {len(images)} images")
        return cors_response({"response": answer, "sessionId": session_id, "images": images})
    
    except Exception as e:
        logger.error(f"❌ Agent query failed: {e}")
        return cors_response({"error": str(e)}, 500)

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
        logger.error(f"❌ Get image error: {e}")
        return cors_response({"error": str(e)}, 500)


# -----------------------------------------------------------
# Lambda Entrypoint
# -----------------------------------------------------------
def lambda_handler(event, context):
    """Main Lambda handler for API Gateway and Bedrock Agent requests."""
    logger.info(f"🤖 Lambda triggered: {json.dumps(event)[:500]}")
    
    # Check if this is a Bedrock Agent action invocation
    if "messageVersion" in event and "agent" in event:
        logger.info("🤖 Bedrock Agent action invocation detected")
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
    logger.info(f"📍 Raw path: {path} | Method: {method}")

    if path.startswith("/default/"):
        path = path[8:]
    elif path.startswith("/prod/"):
        path = path[5:]
    
    logger.info(f"🔄 Cleaned path: {path}")

    if method == "OPTIONS":
        return cors_response()

    try:
        if path == "/get-upload-url" and method in ["GET", "POST"]:
            return handle_get_upload_url_api(event)
        elif path == "/list-files" and method == "GET":
            return handle_list_files_api(event)
        elif path == "/delete-file" and method in ["DELETE", "GET"]:
            return handle_delete_file_api(event)
        elif path == "/agent-query" and method == "POST":
            return handle_agent_query(event)
        elif path == "/get-image" and method == "GET":
            return handle_get_image(event)
        else:
            logger.error(f"Unhandled route: {path}")
            return cors_response({"error": f"Unhandled route: {path}"}, 404)

    except Exception as e:
        logger.error(f"Lambda error: {e}")
        return cors_response({"error": str(e)}, 500)
