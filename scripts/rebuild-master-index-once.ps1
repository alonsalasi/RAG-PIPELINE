# One-time script to rebuild master index with ALL existing documents
# This fixes the issue where old documents aren't searchable

Write-Host "Rebuilding master index with all existing documents..." -ForegroundColor Yellow

# Invoke the agent Lambda to rebuild the index
aws lambda invoke `
    --function-name pdfquery-agent-executor `
    --invocation-type Event `
    --payload '{"action":"rebuild_index"}' `
    response.json

Write-Host "✅ Index rebuild triggered. This will take a few minutes." -ForegroundColor Green
Write-Host "Check CloudWatch logs for progress: /aws/lambda/pdfquery-agent-executor" -ForegroundColor Cyan
