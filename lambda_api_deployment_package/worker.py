import os
import boto3
import json
import time
from urllib.parse import urlparse
from io import BytesIO
from botocore.exceptions import ClientError
from PIL import Image

# --- Tesseract Imports ---
import pytesseract

# --- RAG Core Imports (Minimal for Ingestion) ---
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema.document import Document
# NOTE: Removed dependency on numpy/faiss here. We assume they exist in the execution environment
# if vectorization logic is re-added, but for pure chunking, these are minimal.

# --- Configuration (from Lambda Environment Variables) ---
S3_DOCUMENTS_BUCKET = os.environ.get("S3_DOCUMENTS_BUCKET")
AWS_REGION = os.environ.get("AWS_REGION", "us-west-2")

# --- FAISS/S3 Persistence Constants ---
FAISS_INDEX_KEY = "faiss_index/index.faiss" 
DOCSTORE_KEY = "faiss_index/docstore.json"
FAISS_LOCAL_PATH = "/tmp/faiss_index/" 

# --- RAG/LLM Constants ---
# Bedrock Titan is the standard choice for RAG embeddings
EMBEDDING_MODEL_ID = 'amazon.titan-embed-text-v1' 
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

# Initialize Boto3 clients
sqs = boto3.client('sqs', region_name=AWS_REGION)
s3_client = boto3.client('s3', region_name=AWS_REGION)
bedrock_client = boto3.client('bedrock-runtime', region_name=AWS_REGION)


# Initialize RAG components once
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n\n", "\n", " ", ""]
)


# --- Tesseract-based Extraction Logic ---

def extract_text_with_tesseract(bucket, key):
    """Downloads file from S3 and extracts text using Tesseract (Hebrew/English)."""
    print(f"Downloading s3://{bucket}/{key} for Tesseract processing...")
    
    # Download file content into memory
    response = s3_client.get_object(Bucket=bucket, Key=key)
    file_bytes = BytesIO(response['Body'].read())
    
    # Use Pillow to open the image/PDF and pytesseract for OCR
    try:
        image = Image.open(file_bytes)
        extracted_text = pytesseract.image_to_string(
            image, 
            lang='heb+eng' # Use both Hebrew and English language packs
        )
        return extracted_text
    except Exception as e:
        print(f"Tesseract or Image loading failed: {e}")
        raise

# --- Core Worker Logic ---

def process_message(message_body):
    """
    Handles the entire RAG ingestion pipeline for one document.
    NOTE: FAISS/Vectorization removed due to Lambda size constraints.
    """
    
    # 1. Parse SQS/SNS Message to get S3 Key
    try:
        sns_message = json.loads(message_body)
        s3_record = json.loads(sns_message['Message'])['Records'][0]['s3']
        bucket = s3_record['bucket']['name']
        key = urlparse(s3_record['object']['key']).path.lstrip('/') 
    except (KeyError, json.JSONDecodeError) as e:
        print(f"ERROR: Message format is incorrect. {e}")
        return False
    
    # 2. Tesseract Extraction Workflow
    try:
        raw_text = extract_text_with_tesseract(bucket, key)

        if not raw_text.strip():
            print(f"WARNING: Tesseract extracted no readable text from {key}. Skipping.")
            s3_client.delete_object(Bucket=bucket, Key=key)
            return True 
        
        print(f"Successfully extracted {len(raw_text)} characters from {key}")

    except Exception as e:
        print(f"CRITICAL TESSERACT FAILURE processing {key}: {e}")
        return False 
        
    # 3. RAG Pipeline: Chunking and Saving to JSON
    try:
        # Create a document object with metadata
        doc = [Document(page_content=raw_text, metadata={"source_key": key, "s3_bucket": bucket})]
        documents = text_splitter.split_documents(doc)
        
        # NOTE: Vector indexing logic is GONE. We are only saving the chunks for keyword search.
        
        chunk_key = f"processed_chunks/{key}.json"
        
        # Simple serialization of chunks to JSON (simulates saving vector index)
        serializable_documents = [
            {"page_content": d.page_content, "metadata": d.metadata} for d in documents
        ]

        s3_client.put_object(
            Bucket=bucket,
            Key=chunk_key,
            Body=json.dumps(serializable_documents),
            ContentType='application/json'
        )
        
        # 4. Delete the file from the 'incoming/' folder to mark it as processed
        s3_client.delete_object(Bucket=bucket, Key=key)
        
        print(f"--- Document '{key}' fully processed, chunked, and saved to {chunk_key}. ---")
        return True

    except Exception as e:
        print(f"CRITICAL CHUNKING/SAVING FAILURE processing {key}: {e}")
        return False 


def start_worker():
    """Placeholder for the old ECS worker loop (now handled by Lambda Event Source Mapping)."""
    pass

if __name__ == "__main__":
    from langchain.schema.document import Document
    pass
