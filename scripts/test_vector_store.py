import boto3
import json

# Download and check a processed file
s3 = boto3.client('s3')
response = s3.get_object(Bucket='pdfquery-rag-documents-production', Key='processed/Cherry.json')
data = json.loads(response['Body'].read())

print("Cherry.json images:")
for img in data.get('images', [])[:3]:
    print(f"  - Page {img['page']}: {img['s3_key']}")
    print(f"    Description: {img['description'][:100]}...")
    print()
