import boto3
import time

s3 = boto3.client('s3')
bucket = 'pdfquery-rag-documents-production'

# Get all uploads
uploads_resp = s3.list_objects_v2(Bucket=bucket, Prefix='uploads/')
upload_keys = [obj['Key'] for obj in uploads_resp.get('Contents', [])]

# Get all processed
processed_resp = s3.list_objects_v2(Bucket=bucket, Prefix='processed/')
processed_keys = [obj['Key'] for obj in processed_resp.get('Contents', [])]

# Extract base names
upload_bases = {}
for key in upload_keys:
    filename = key.replace('uploads/', '')
    if '.' in filename:
        base = filename.rsplit('.', 1)[0]
        upload_bases[base] = key

processed_bases = set()
for key in processed_keys:
    filename = key.replace('processed/', '').replace('.json', '')
    if '_' in filename:
        parts = filename.split('_', 1)
        if parts[0].isdigit() and len(parts[0]) == 10:
            filename = parts[1]
    processed_bases.add(filename)

# Find unprocessed
unprocessed = []
for base, key in upload_bases.items():
    if base not in processed_bases:
        unprocessed.append(key)

print(f"Found {len(unprocessed)} unprocessed files")
print("Triggering reprocessing...\n")

# Trigger reprocessing by updating metadata
for key in unprocessed:
    try:
        s3.copy_object(
            Bucket=bucket,
            CopySource={'Bucket': bucket, 'Key': key},
            Key=key,
            Metadata={'reprocess': str(int(time.time()))},
            MetadataDirective='REPLACE'
        )
        print(f"Triggered: {len(key)} chars")
    except Exception as e:
        print(f"Failed: {str(e)[:50]}")
