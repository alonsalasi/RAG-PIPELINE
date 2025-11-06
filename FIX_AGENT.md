# Fix: Agent Not Searching PDFs

## Problem
Your Bedrock Agent responds to questions but doesn't search your FAISS vector store with PDFs.

## Solution Applied

### 1. Updated Agent Instructions (agent.tf)
Changed from overly strict instructions to clearer, simpler ones that explicitly tell the agent to use the `search_documents` tool.

### 2. Enhanced Logging (agent_executor.py)
Added detailed logging to track when search is called:
- "🔍 SEARCH ACTION CALLED" when agent uses search
- "🔍 SEARCH QUERY: [query]" shows what's being searched
- "✅ SEARCH COMPLETE" confirms results returned

## How to Apply the Fix

### Option 1: Quick Update (Recommended)
```bash
# Run the update script
.\update_agent.ps1
```

### Option 2: Manual Steps
```bash
# 1. Apply terraform changes
terraform apply -target=aws_bedrockagent_agent.rag_agent -auto-approve

# 2. Get agent ID
$AGENT_ID = terraform output -raw bedrock_agent_id

# 3. Prepare agent (creates new DRAFT version)
aws bedrock-agent prepare-agent --agent-id $AGENT_ID --region us-east-1

# 4. Wait 30 seconds for preparation to complete
```

### Option 3: Update via AWS Console
1. Go to AWS Console → Bedrock → Agents
2. Select your agent
3. Click "Edit" on Agent Instructions
4. Replace with the new instruction from agent.tf
5. Click "Save and exit"
6. Click "Prepare" to create new version

## Testing the Fix

### 1. Deploy Updated Lambda
```bash
cd Lambda
terraform apply -target=aws_lambda_function.agent_executor -auto-approve
```

### 2. Test the Agent
Ask a question about your PDFs through your application.

### 3. Check CloudWatch Logs
Go to CloudWatch → Log Groups → `/aws/lambda/pdfquery-agent-executor`

You should see:
```
🔍 SEARCH ACTION CALLED - Agent is searching PDFs
🔍 SEARCH QUERY: [your question]
⏱️ SEARCH: Vector search (k=30) took 0.XXXs, found 30 results
✅ SEARCH COMPLETE - Returning 30 results to agent
```

## If Search is Still Not Called

The agent might be using an old version. You need to:

### Create New Version and Update Alias
1. Go to AWS Console → Bedrock → Agents → Your Agent
2. Click "Create version" button
3. Note the version number (e.g., "2")
4. Go to "Aliases" tab
5. Click on your production alias (ID: 2XEBVXAZYI)
6. Click "Edit"
7. Select the new version you just created
8. Click "Save"

## Verification

After applying the fix, test with:
- "What documents do you have?"
- "Tell me about [topic in your PDF]"
- "Search for [keyword]"

The agent should now:
1. Call the search action (visible in logs)
2. Return information from your PDFs
3. Cite the source document

## Troubleshooting

### Agent still not searching?
- Check CloudWatch logs for "SEARCH ACTION CALLED"
- If not present, the agent is using an old version
- Create new version and update alias (see above)

### Search called but no results?
- Check if PDFs are in FAISS index: Look for "Preloaded master index: X vectors"
- Verify processed/ folder in S3 has .json files
- Check vector_store/master/ has index.faiss and index.pkl

### Agent returns "I don't have access to documents"?
- This means search is NOT being called
- Agent is using old instructions
- Follow "Create New Version and Update Alias" steps above
