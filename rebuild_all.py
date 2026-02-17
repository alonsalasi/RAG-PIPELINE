import boto3
import time

s3 = boto3.client('s3')
bucket = 'pdfquery-rag-documents-production'

# Get all uploads
response = s3.list_objects_v2(Bucket=bucket, Prefix='uploads/')
uploads = [obj['Key'] for obj in response.get('Contents', [])]

print(f"Found {len(uploads)} files to reprocess")
print("This will rebuild the complete master index from all documents")
print("Estimated time: 5-10 minutes")

input("Press Enter to continue...")

for i, key in enumerate(uploads, 1):
    try:
        s3.copy_object(
            Bucket=bucket,
            CopySource={'Bucket': bucket, 'Key': key},
            Key=key,
            Metadata={'rebuild': str(int(time.time()))},
            MetadataDirective='REPLACE'
        )
        print(f"{i}/{len(uploads)}: Triggered {key.split('/')[-1][:50]}")
        time.sleep(0.5)  # Throttle to avoid overwhelming Lambda
    except Exception as e:
        print(f"Failed {key}: {e}")
