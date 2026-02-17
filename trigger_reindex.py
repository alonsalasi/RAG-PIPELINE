import boto3
import json

s3 = boto3.client('s3', verify=False)
sqs = boto3.client('sqs', verify=False)

BUCKET = 'pdfquery-rag-documents-production'
QUEUE_URL = 'https://sqs.us-east-1.amazonaws.com/656008069461/pdfquery-ingestion-queue'

# List all files in uploads/
response = s3.list_objects_v2(Bucket=BUCKET, Prefix='uploads/')

if 'Contents' not in response:
    print("No files found")
    exit()

files = [obj['Key'] for obj in response['Contents']]
print(f"Found {len(files)} files to reprocess")

# Send SQS message for each file
for s3_key in files:
    message = {
        "Records": [{
            "eventVersion": "2.1",
            "eventSource": "aws:s3",
            "eventName": "ObjectCreated:Put",
            "s3": {
                "bucket": {"name": BUCKET},
                "object": {"key": s3_key}
            }
        }]
    }
    
    sqs.send_message(QueueUrl=QUEUE_URL, MessageBody=json.dumps(message))
    print(f"Queued: {s3_key}")

print(f"\n✅ Sent {len(files)} files to processing queue")
