import boto3, json

client = boto3.client('lambda')
resp = client.invoke(
    FunctionName='pdfquery-agent-executor',
    InvocationType='Event',
    Payload=json.dumps({"action": "rebuild_index"}).encode()
)
print("StatusCode:", resp['StatusCode'])
print("Rebuild triggered successfully")
