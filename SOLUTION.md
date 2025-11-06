# Solution: Agent Not Searching PDFs

## Problem Identified

Your Bedrock Agent is **NOT calling the `/search` action** to retrieve information from your FAISS vector store. The agent responds directly without searching your PDFs.

Evidence from logs:
- Agent invocation takes 7.7 seconds
- No "🔍 SEARCH ACTION CALLED" log appears
- Agent returns generic responses instead of PDF content

## Root Cause

The Bedrock Agent doesn't know it should use the search tool. This is a **configuration issue**, not a code issue.

## Solution Steps

### Step 1: Update Lambda Code (DONE ✅)

I've updated `agent_executor.py` with better logging:
- Added "🔍 SEARCH ACTION CALLED" log when search is invoked
- Enabled trace logging to see agent actions
- Added detailed trace output

### Step 2: Test Current Configuration

Run the diagnostic script:

```bash
# Set your environment variables
export BEDROCK_AGENT_ID="your-agent-id"
export BEDROCK_AGENT_ALIAS_ID="your-alias-id"
export AWS_REGION="us-east-1"

# Run test
python test_agent.py
```

This will tell you if the agent is calling search or not.

### Step 3: Fix Agent Instructions

Go to AWS Console → Bedrock → Agents → [Your Agent] → Edit

**Update Agent Instructions to:**

```
You are a helpful AI assistant that answers questions about PDF documents that have been uploaded to the system.

CRITICAL INSTRUCTIONS:
1. When users ask ANY question about documents, content, or information, you MUST use the search tool FIRST
2. Call the search action with the user's query to retrieve relevant information from the PDFs
3. Base your answer ONLY on the search results returned
4. If search returns no results, tell the user the information is not available in the uploaded documents
5. Always cite which document the information came from using the source metadata

WORKFLOW:
User Question → Use Search Tool → Analyze Results → Provide Answer

Example:
User: "What is the company name?"
You: [Call search("company name")] → [Get results] → "According to [document name], the company name is XYZ Corp."

Never answer questions about document content without searching first.
```

### Step 4: Verify Action Group

Ensure your action group is configured:

1. Go to your agent → Action Groups
2. Verify you have an action group with:
   - **API Path**: `/search`
   - **Method**: POST
   - **Parameter**: `query` (string, required)
   - **Lambda Function**: Your agent_executor Lambda

### Step 5: Create New Version & Update Alias

After updating instructions:
1. Click "Prepare" to create a new version
2. Go to Aliases
3. Update your alias to point to the new version

### Step 6: Test Again

1. Deploy updated Lambda code
2. Test with: "What documents do you have?"
3. Check CloudWatch logs for "🔍 SEARCH ACTION CALLED"

## Expected Behavior After Fix

**Before (Current):**
```
User: "What is in the PDF?"
Agent: "I don't have access to specific PDFs..." (7 seconds)
Logs: No search action called
```

**After (Fixed):**
```
User: "What is in the PDF?"
Agent: [Calls search] → "According to document.pdf, it contains..." (7 seconds)
Logs: 🔍 SEARCH ACTION CALLED - Agent is searching PDFs
      🔍 SEARCH QUERY: What is in the PDF?
      ✅ SEARCH COMPLETE - Returning 30 results to agent
```

## Quick Verification

After making changes, check CloudWatch Logs for your Lambda:

```
✅ Should see: "🔍 SEARCH ACTION CALLED"
✅ Should see: "🔍 SEARCH QUERY: [user's question]"
✅ Should see: "✅ SEARCH COMPLETE - Returning X results"
```

If you DON'T see these logs, the agent is still not calling search.

## Alternative: Direct Search Test

If agent still doesn't work, you can test the search endpoint directly:

```bash
curl -X POST https://your-api-gateway/agent-query \
  -H "Content-Type: application/json" \
  -d '{"query": "What documents do you have?"}'
```

This bypasses the agent and calls your Lambda directly to verify search works.

## Need More Help?

1. Run `python test_agent.py` and share the output
2. Check CloudWatch logs after asking a question
3. Share your agent instructions from AWS Console
4. Verify action group configuration in Bedrock console
