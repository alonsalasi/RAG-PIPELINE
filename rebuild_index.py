import boto3
import json
import sys

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Initialize Lambda client
lambda_client = boto3.client('lambda', region_name='us-east-1')

# Get Lambda function name from environment or use default
LAMBDA_FUNCTION_NAME = 'pdfquery-agent-executor'

print("Triggering master index rebuild...")

try:
    response = lambda_client.invoke(
        FunctionName=LAMBDA_FUNCTION_NAME,
        InvocationType='RequestResponse',
        Payload=json.dumps({"action": "rebuild_index"})
    )
    
    result = json.loads(response['Payload'].read())
    
    if response['StatusCode'] == 200:
        print("SUCCESS: Index rebuild completed!")
        print(f"Response: {result}")
    else:
        print(f"FAILED: Index rebuild failed with status {response['StatusCode']}")
        print(f"Response: {result}")
        
except Exception as e:
    print(f"ERROR: {e}")
