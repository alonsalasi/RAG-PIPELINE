#!/usr/bin/env python3
"""Rebuild vector index from existing processed JSONs"""
import boto3
import json
import os
import tempfile
from langchain_aws import BedrockEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.docstore.document import Document

BUCKET = "pdfquery-rag-documents-production"
REGION = "us-east-1"

s3 = boto3.client('s3', region_name=REGION)

# Get all processed JSONs
response = s3.list_objects_v2(Bucket=BUCKET, Prefix="processed/")
processed_files = [obj['Key'] for obj in response.get('Contents', []) if obj['Key'].endswith('.json')]

print(f"Found {len(processed_files)} processed files")

all_docs = []

for key in processed_files:
    print(f"\nProcessing {key}...")
    obj = s3.get_object(Bucket=BUCKET, Key=key)
    data = json.loads(obj['Body'].read())
    
    base_name = key.split('/')[-1].replace('.json', '')
    
    # Add image documents with specifications
    images = data.get('images', [])
    print(f"  Found {len(images)} images")
    
    for img in images:
        desc = img.get('description', '')
        page = img.get('page', 0)
        s3_key = img.get('s3_key', '')
        
        # Create searchable content with IMAGE_URL marker
        content = f"Document: {base_name}\nPage {page}: {desc}\nIMAGE_URL:{s3_key}|PAGE:{page}|SOURCE:{base_name}"
        
        doc = Document(
            page_content=content,
            metadata={
                "source": base_name,
                "type": "image",
                "page": page,
                "s3_key": s3_key
            }
        )
        all_docs.append(doc)
        print(f"    Added image doc from page {page} ({len(desc)} chars)")

print(f"\nTotal documents to index: {len(all_docs)}")

if not all_docs:
    print("ERROR: No documents to index!")
    exit(1)

# Create embeddings
print("\nCreating embeddings...")
embeddings = BedrockEmbeddings(
    model_id="cohere.embed-multilingual-v3",
    region_name=REGION
)

# Create FAISS index
print("Building FAISS index...")
vector_store = FAISS.from_documents(all_docs, embeddings)
print(f"Index created with {vector_store.index.ntotal} vectors")

# Save and upload
with tempfile.TemporaryDirectory() as tmpdir:
    print(f"\nSaving index to {tmpdir}...")
    vector_store.save_local(tmpdir)
    
    print("Uploading to S3...")
    s3.upload_file(
        os.path.join(tmpdir, "index.faiss"),
        BUCKET,
        "vector_store/master/index.faiss"
    )
    s3.upload_file(
        os.path.join(tmpdir, "index.pkl"),
        BUCKET,
        "vector_store/master/index.pkl"
    )

print("\n✅ Index rebuilt successfully!")
print(f"Total vectors: {vector_store.index.ntotal}")
