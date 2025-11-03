"""
Rebuild master FAISS index with IMAGE_URL embedded in content.
Run this once after deploying the new Lambda code.
"""
import boto3
import json
import os

# Get configuration from environment
REGION = os.environ.get('AWS_REGION', 'us-east-1')
FUNCTION_NAME = os.environ.get('LAMBDA_FUNCTION_NAME', 'pdfquery-agent-executor')

try:
    lambda_client = boto3.client('lambda', region_name=REGION)
    
    # Simulate API Gateway event to trigger rebuild
    event = {
        "path": "/production/delete-file",
        "httpMethod": "DELETE",
        "queryStringParameters": {
            "fileName": "_trigger_rebuild_dummy.json"
        }
    }
    
    print(f"Triggering master index rebuild on {FUNCTION_NAME}...")
    response = lambda_client.invoke(
        FunctionName=FUNCTION_NAME,
        InvocationType='RequestResponse',
        Payload=json.dumps(event)
    )
    
    result = json.loads(response['Payload'].read())
    print(f"Response: {result}")
    print("\nMaster index rebuild triggered!")
    print("Test query: 'show me a cherry car in red'")
except Exception as e:
    print(f"Error: {type(e).__name__}: {str(e)}")
