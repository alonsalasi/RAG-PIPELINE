import boto3
import json

s3 = boto3.client('s3')
bucket = 'pdfquery-rag-documents-production'

# Get all uploads
uploads_resp = s3.list_objects_v2(Bucket=bucket, Prefix='uploads/')
upload_keys = [obj['Key'] for obj in uploads_resp.get('Contents', [])]

# Get all processed
processed_resp = s3.list_objects_v2(Bucket=bucket, Prefix='processed/')
processed_keys = [obj['Key'] for obj in processed_resp.get('Contents', [])]

# Extract base names
upload_bases = set()
for key in upload_keys:
    filename = key.replace('uploads/', '')
    if '.' in filename:
        base = filename.rsplit('.', 1)[0]
        upload_bases.add((base, key))

processed_bases = set()
for key in processed_keys:
    filename = key.replace('processed/', '').replace('.json', '')
    # Remove timestamp prefix
    if '_' in filename:
        parts = filename.split('_', 1)
        if parts[0].isdigit() and len(parts[0]) == 10:
            filename = parts[1]
    processed_bases.add(filename)

# Find unprocessed
unprocessed = []
for base, key in upload_bases:
    if base not in processed_bases:
        unprocessed.append(key)

print(f"Total uploads: {len(upload_bases)}")
print(f"Total processed: {len(processed_bases)}")
print(f"Unprocessed: {len(unprocessed)}")
print("\nUnprocessed S3 keys:")
for key in sorted(unprocessed):
    print(key)

# Save to file
with open('unprocessed_keys.txt', 'w', encoding='utf-8') as f:
    for key in sorted(unprocessed):
        f.write(key + '\n')
