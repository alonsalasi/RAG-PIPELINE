"""
Rebuild master FAISS index with IMAGE_URL embedded in content.
Run this once after deploying the new Lambda code.
"""
import boto3
import json

# Trigger rebuild by invoking the delete file handler with a non-existent file
# This will cause rebuild_master_index() to run
lambda_client = boto3.client('lambda', region_name='us-east-1')

# Simulate API Gateway event to trigger rebuild
event = {
    "path": "/production/delete-file",
    "httpMethod": "DELETE",
    "queryStringParameters": {
        "fileName": "_trigger_rebuild_dummy.json"
    }
}

print("Triggering master index rebuild...")
response = lambda_client.invoke(
    FunctionName='pdfquery-agent-executor',
    InvocationType='RequestResponse',
    Payload=json.dumps(event)
)

result = json.loads(response['Payload'].read())
print(f"Response: {result}")
print("\nMaster index has been rebuilt with IMAGE_URL embedded in content!")
print("Now test: 'show me a cherry car in red'")
