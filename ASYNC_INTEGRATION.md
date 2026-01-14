# Integration Instructions for Async Agent Query

## Changes Made:

1. **Deleted websocket.tf** - WebSocket infrastructure removed
2. **Updated API_Gateway.tf** - Added `/agent-status` route
3. **Updated index.html** - Replaced WebSocket with HTTP polling
4. **Created agent_executor_async.py** - New async handler functions

## Steps to Integrate:

### 1. Update Lambda/agent_executor.py

Add these 3 functions from `agent_executor_async.py` to your `agent_executor.py`:

- `handle_agent_query_async()` - Starts async query, returns queryId
- `process_agent_query_background()` - Processes query in background
- `handle_agent_status()` - Returns query status

### 2. Update lambda_handler() routing

Find the section with path routing and UPDATE:

```python
elif path == "/agent-query" and method == "POST":
    return handle_agent_query_async(event)  # Changed from handle_agent_query
```

ADD new route:

```python
elif path == "/agent-status" and method == "GET":
    return handle_agent_status(event)
```

### 3. Add async action handler

In `lambda_handler()`, after the warmup ping handler, ADD:

```python
# Handle async agent query processing
if event.get("action") == "process_agent_query":
    query_id = event.get("queryId")
    query = event.get("query")
    session_id = event.get("sessionId")
    process_agent_query_background(query_id, query, session_id)
    return {"statusCode": 200}
```

### 4. Remove WebSocket code

DELETE these functions from agent_executor.py:
- `handle_websocket_authorizer()`
- `generate_auth_policy()`
- `send_websocket_message()`
- `handle_websocket_agent_query()`

DELETE WebSocket routing in `lambda_handler()`:
- Remove the entire `if route_key in ['$connect', '$disconnect', 'query']:` block

### 5. Deploy

```powershell
# Build and push Lambda
cd Lambda
.\agent_cache_build_push.bat

# Apply Terraform
cd ..
terraform apply
```

## How It Works:

1. User submits query → `/agent-query` returns `queryId` immediately
2. Lambda invokes itself async to process query in background
3. Background process writes status to `s3://bucket/agent-status/{queryId}.json`
4. Frontend polls `/agent-status?queryId=xxx` every 1 second
5. When status is "completed", frontend displays response and deletes S3 file

## Benefits:

- No 30-second API Gateway timeout
- No WebSocket infrastructure costs
- Simpler architecture
- Works with existing retry logic
- Automatic cleanup of status files
