import json
import boto3
import os
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize clients
apigateway_management = None

def get_apigateway_client(connection_url):
    """Get API Gateway Management API client for sending messages to WebSocket connections."""
    global apigateway_management
    if apigateway_management is None:
        apigateway_management = boto3.client(
            'apigatewaymanagementapi',
            endpoint_url=connection_url
        )
    return apigateway_management

def lambda_handler(event, context):
    """Handle WebSocket events: connect, disconnect, and messages."""
    route_key = event.get('requestContext', {}).get('routeKey')
    connection_id = event.get('requestContext', {}).get('connectionId')
    domain_name = event.get('requestContext', {}).get('domainName')
    stage = event.get('requestContext', {}).get('stage')
    
    connection_url = f"https://{domain_name}/{stage}"
    
    logger.info(f"Route: {route_key}, ConnectionId: {connection_id}")
    
    if route_key == '$connect':
        return handle_connect(connection_id)
    elif route_key == '$disconnect':
        return handle_disconnect(connection_id)
    elif route_key == 'query':
        return handle_query(event, connection_id, connection_url)
    else:
        return {'statusCode': 400, 'body': 'Unknown route'}

def handle_connect(connection_id):
    """Handle new WebSocket connection."""
    logger.info(f"Client connected: {connection_id}")
    return {'statusCode': 200, 'body': 'Connected'}

def handle_disconnect(connection_id):
    """Handle WebSocket disconnection."""
    logger.info(f"Client disconnected: {connection_id}")
    return {'statusCode': 200, 'body': 'Disconnected'}

def handle_query(event, connection_id, connection_url):
    """Handle query message and invoke agent executor asynchronously."""
    try:
        body = json.loads(event.get('body', '{}'))
        query = body.get('query', '')
        session_id = body.get('sessionId', '')
        
        if not query:
            send_message(connection_id, connection_url, {
                'type': 'error',
                'message': 'Query is required'
            })
            return {'statusCode': 400, 'body': 'Query required'}
        
        logger.info(f"Processing query for connection {connection_id}")
        
        # Send acknowledgment
        send_message(connection_id, connection_url, {
            'type': 'status',
            'message': 'Processing your query...'
        })
        
        # Invoke agent executor Lambda asynchronously with connection info
        lambda_client = boto3.client('lambda')
        lambda_client.invoke(
            FunctionName=os.environ['AGENT_EXECUTOR_FUNCTION'],
            InvocationType='Event',
            Payload=json.dumps({
                'websocket': True,
                'connectionId': connection_id,
                'connectionUrl': connection_url,
                'body': json.dumps({
                    'query': query,
                    'sessionId': session_id
                })
            })
        )
        
        return {'statusCode': 200, 'body': 'Query submitted'}
        
    except Exception as e:
        logger.error(f"Error handling query: {e}")
        send_message(connection_id, connection_url, {
            'type': 'error',
            'message': str(e)
        })
        return {'statusCode': 500, 'body': 'Internal error'}

def send_message(connection_id, connection_url, message):
    """Send message to WebSocket connection."""
    try:
        client = get_apigateway_client(connection_url)
        client.post_to_connection(
            ConnectionId=connection_id,
            Data=json.dumps(message).encode('utf-8')
        )
    except Exception as e:
        logger.error(f"Failed to send message to {connection_id}: {e}")
