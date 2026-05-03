import boto3, sys, io, datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

client = boto3.client('logs')

# Get latest 5 streams
streams = client.describe_log_streams(
    logGroupName='/aws/lambda/pdfquery-agent-executor',
    orderBy='LastEventTime',
    descending=True,
    limit=5
)['logStreams']

keywords = ['too long', 'input', 'token', 'limit', 'ValidationException', 'context', 
            'length', 'ERROR', 'failed', 'history', 'session', 'compress', 'truncat',
            'conversationHistory', 'sessionAttributes', 'max_token', 'exceeded']

for stream in streams:
    last_event = stream.get('lastEventTimestamp', 0)
    dt = datetime.datetime.fromtimestamp(last_event/1000).strftime('%Y-%m-%d %H:%M:%S') if last_event else 'never'
    print(f"\n=== Stream: {dt} ===")
    
    resp = client.get_log_events(
        logGroupName='/aws/lambda/pdfquery-agent-executor',
        logStreamName=stream['logStreamName'],
        limit=500
    )
    
    for e in resp['events']:
        msg = e['message']
        if any(k.lower() in msg.lower() for k in keywords):
            print(msg[:500])
