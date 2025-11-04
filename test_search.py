import boto3
import json

# Test the search function directly
lambda_client = boto3.client('lambda', region_name='us-east-1')

# Test search for Hyundai specifications
test_event = {
    "messageVersion": "1.0",
    "agent": {"name": "test"},
    "actionGroup": "LambdaTools", 
    "apiPath": "/search",
    "httpMethod": "POST",
    "requestBody": {
        "content": {
            "application/json": {
                "properties": [
                    {"name": "query", "value": "Hyundai Tucson dimensions specifications"}
                ]
            }
        }
    }
}

response = lambda_client.invoke(
    FunctionName='pdfquery-agent-executor',
    Payload=json.dumps(test_event)
)

result = json.loads(response['Payload'].read())
print("Search Results:")
print(json.dumps(result, indent=2))