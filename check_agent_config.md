# Bedrock Agent Configuration Checklist

## Problem: Agent is NOT searching your PDFs

Your logs show the agent responds in ~7 seconds but NEVER calls the `/search` action.
This means the agent doesn't know it should search your vector store.

## Required Fixes:

### 1. Check Agent Instructions
Your Bedrock Agent needs instructions like:

```
You are a helpful assistant that answers questions about PDF documents.

IMPORTANT: When users ask questions about documents, you MUST use the search tool to find relevant information from the uploaded PDFs before answering.

Always search the documents first using the search action with the user's query, then provide a comprehensive answer based on the search results.

If no relevant information is found, tell the user that the information is not available in the uploaded documents.
```

### 2. Verify Action Group Configuration

Go to AWS Console → Bedrock → Agents → Your Agent → Action Groups

Check that you have an action group with:
- **Name**: DocumentSearch (or similar)
- **Action**: `/search`
- **Method**: POST
- **Parameters**: 
  - `query` (string, required) - The search query

### 3. Check Agent Prompt Override (if using)

If you have a prompt override, ensure it mentions using the search tool.

### 4. Test the Search Action Directly

Test if the search action works by invoking it directly:

```python
import boto3
import json

bedrock = boto3.client('bedrock-agent-runtime', region_name='us-east-1')

response = bedrock.invoke_agent(
    agentId='YOUR_AGENT_ID',
    agentAliasId='YOUR_ALIAS_ID',
    sessionId='test-session',
    inputText='Search for information about [YOUR TOPIC]',
    enableTrace=True
)

# Check trace to see if search is called
for event in response['completion']:
    if 'trace' in event:
        print(json.dumps(event['trace'], indent=2))
```

### 5. Common Issues:

1. **Agent instructions don't mention searching** - Agent won't know to use the tool
2. **Action group not properly configured** - Lambda won't be called
3. **Lambda permissions missing** - Agent can't invoke Lambda
4. **Wrong API schema** - Agent doesn't understand how to call search

### 6. Quick Fix - Update Agent Instructions

In AWS Console:
1. Go to Bedrock → Agents → [Your Agent]
2. Click "Edit" on Agent Instructions
3. Add this at the beginning:

```
CRITICAL: You MUST use the search tool for ALL questions about documents.
Before answering any question, call the search action with the user's query.
Base your answers ONLY on the search results.
```

4. Save and create a new version
5. Update the alias to point to the new version

### 7. Verify Lambda is Being Called

Check CloudWatch Logs for your Lambda function.
You should see: "🔍 SEARCH ACTION CALLED - Agent is searching PDFs"

If you DON'T see this log, the agent is NOT calling your search function.
