import json
import os
import sys
import boto3
import time
import re
from collections import defaultdict
from botocore.exceptions import ClientError

# CRITICAL FIX 1: Ensure the current directory is in the path for module imports (worker.py)
# This MUST be the first logical code executed.
sys.path.insert(0, os.path.dirname(__file__))

# --- RAG/LLM Imports (CORRECTED) ---
from langchain.chains import RetrievalQA
from langchain_aws import BedrockLLM # Use the dedicated AWS package
from langchain_core.documents import Document # CORRECTED: Document schema is in core

# --- Configuration (from Lambda Environment Variables) ---
S3_DOCUMENTS_BUCKET = os.environ.get("S3_DOCUMENTS_BUCKET")
AWS_REGION = os.environ.get("AWS_REGION", "us-west-2")

# --- Global Constants ---
BEDROCK_MODEL_ID = 'anthropic.claude-v2'
MAX_CONTEXT_CHUNKS = 5

# Initialize Boto3 clients globally (caches across warm calls)
s3_client = boto3.client('s3', region_name=AWS_REGION)
bedrock_client = boto3.client('bedrock-runtime', region_name=AWS_REGION)
# CORRECTED: Use BedrockLLM and pass the client directly
llm = BedrockLLM(client=bedrock_client, model_id=BEDROCK_MODEL_ID)

# Global cache for document content
DOCUMENT_CACHE = {}
LAST_UPDATE_TIME = 0

# --- Core RAG Logic (Simplified Keyword Search) ---

def load_documents_from_s3():
    """
    Loads all chunked documents (JSON files) saved by the ingestion worker into memory.
    """
    global DOCUMENT_CACHE, LAST_UPDATE_TIME

    print("Reloading document cache from S3...")
    new_cache = defaultdict(list)
    
    list_response = s3_client.list_objects_v2(
        Bucket=S3_DOCUMENTS_BUCKET,
        Prefix="processed_chunks/"
    )
    
    contents = list_response.get('Contents', [])
    if not contents:
        print("WARNING: No processed chunk files found in S3.")
        DOCUMENT_CACHE = {}
        return

    for item in contents:
        if not item['Key'].endswith('.json'):
            continue
            
        try:
            obj = s3_client.get_object(Bucket=S3_DOCUMENTS_BUCKET, Key=item['Key'])
            file_content = obj['Body'].read().decode('utf-8')
            chunks_data = json.loads(file_content)

            for chunk_data in chunks_data:
                source_key = chunk_data['metadata']['source_key']
                new_cache[source_key].append(
                    Document(page_content=chunk_data['page_content'], metadata=chunk_data['metadata'])
                )
        except Exception as e:
            print(f"Error loading chunk file {item['Key']}: {e}")
            
    DOCUMENT_CACHE = new_cache
    LAST_UPDATE_TIME = time.time()
    print(f"Successfully loaded {sum(len(v) for v in DOCUMENT_CACHE.values())} chunks into cache.")


def simple_keyword_retriever(query: str) -> list[Document]:
    """
    Performs a simple keyword matching across all loaded documents.
    """
    if not DOCUMENT_CACHE:
        return []

    query_tokens = set(re.findall(r'\b\w+\b', query.lower()))
    scored_chunks = []
    
    for _, doc_chunks in DOCUMENT_CACHE.items():
        for chunk in doc_chunks:
            content = chunk.page_content.lower()
            score = sum(1 for token in query_tokens if token in content)
            if score > 0:
                scored_chunks.append((score, chunk))

    scored_chunks.sort(key=lambda x: x[0], reverse=True)
    return [chunk for score, chunk in scored_chunks[:MAX_CONTEXT_CHUNKS]]


def invoke_rag_chain(query: str, retrieved_context: list[Document]):
    """
    Generates the final response using Bedrock and the provided context.
    """
    context_text = "\n---\n".join([d.page_content for d in retrieved_context])
    source_keys = [d.metadata.get('source_key') for d in retrieved_context]
    
    prompt_template = f"""
You are a professional RAG (Retrieval-Augmented Generation) assistant. 
Answer the user's question ONLY based on the context provided below. 
Do not use external knowledge. If the context does not contain the answer, state that you do not know.

--- CONTEXT ---
{context_text}

--- USER QUESTION ---
{query}
"""
    
    # CORRECTED: .invoke() now returns a direct string
    response_text = llm.invoke(prompt_template)
    
    # CORRECTED: Return is indented and uses the response_text variable
    return {
        'response': response_text,
        'source_documents': source_keys
    }


def get_presigned_url(file_name, file_type):
    """Generates a presigned URL for secure, direct S3 upload from the client."""
    object_key = f"incoming/{file_name}"

    url = s3_client.generate_presigned_url(
        ClientMethod='put_object',
        Params={
            'Bucket': S3_DOCUMENTS_BUCKET,
            'Key': object_key,
            'ContentType': file_type
        },
        ExpiresIn=300
    )
    return url


# --- Lambda Handler (Entry Point) ---

def lambda_handler(event, context):
    
    # CRITICAL: Import worker here after sys.path has been modified to avoid import errors
    import worker 
    
    CORS_HEADERS = {
        'Access-Control-Allow-Origin': '*', 
        'Access-Control-Allow-Methods': 'GET, POST, PUT, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, X-Amz-Date, Authorization, X-Api-Key, X-Amz-Security-Token'
    }

    if event.get('httpMethod') == 'OPTIONS':
        return {'statusCode': 200, 'headers': CORS_HEADERS}
    
    path = event.get('path', '/')

    if path == '/get-upload-url' and event.get('httpMethod') == 'GET':
        try:
            params = event.get('queryStringParameters', {})
            file_name = params.get('fileName')
            file_type = params.get('fileType')
            
            if not file_name or not file_type:
                return {'statusCode': 400, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Missing fileName or fileType parameter.'})}

            signed_url = get_presigned_url(file_name, file_type)
            
            return {
                'statusCode': 200,
                'headers': CORS_HEADERS,
                'body': json.dumps({'signedUrl': signed_url})
            }
        except Exception as e:
            print(f"Error generating presigned URL: {e}")
            return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Failed to generate upload URL', 'details': str(e)})}

    if path == '/query' and event.get('httpMethod') == 'POST':
        try:
            if not DOCUMENT_CACHE: 
                load_documents_from_s3()
        except Exception as e:
            return {'statusCode': 503, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'RAG system offline. Document cache load failed.', 'details': str(e)})}
            
        try:
            body = json.loads(event.get('body', '{}'))
            query = body.get('query')

            if not query:
                return {'statusCode': 400, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Missing query parameter.'})}

            context_documents = simple_keyword_retriever(query)

            if not context_documents:
                return {'statusCode': 200, 'headers': CORS_HEADERS, 'body': json.dumps({'response': 'I could not find any relevant documents in the knowledge base to answer your question.', 'source_documents': []})}

            result = invoke_rag_chain(query, context_documents)
            
            return {
                'statusCode': 200,
                'headers': CORS_HEADERS,
                'body': json.dumps({
                    'response': result['response'],
                    'source_documents': result['source_documents']
                })
            }

        except Exception as e:
            print(f"Error processing query: {e}")
            return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Internal processing error.', 'details': str(e)})}
    
    if path == '/health' and event.get('httpMethod') == 'GET':
        status = "ok" if DOCUMENT_CACHE else "loading/degraded (Document cache empty)"
        return {'statusCode': 200, 'headers': CORS_HEADERS, 'body': json.dumps({"status": status, "service": "rag-api"})}
        
    return {'statusCode': 404, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Resource not found'})}