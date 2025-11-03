import boto3
import json
import os

# Get bucket from environment or use default
BUCKET = os.environ.get('S3_BUCKET', 'pdfquery-rag-documents-production')
FILE_KEY = 'processed/Cherry.json'

try:
    s3 = boto3.client('s3')
    response = s3.get_object(Bucket=BUCKET, Key=FILE_KEY)
    data = json.loads(response['Body'].read())
    
    print(f"File: {FILE_KEY}")
    print(f"Images found: {len(data.get('images', []))}")
    print("\nFirst 3 images:")
    for img in data.get('images', [])[:3]:
        print(f"  - Page {img['page']}: {img['s3_key']}")
        desc = img.get('description', 'No description')
        print(f"    Description: {desc[:100]}...")
        print()
except Exception as e:
    print(f"Error: {type(e).__name__}: {str(e)}")
