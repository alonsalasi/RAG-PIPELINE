Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Updating Bedrock Agent Configuration" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Step 1: Applying Terraform changes..." -ForegroundColor Yellow
terraform apply -target=aws_bedrockagent_agent.rag_agent -auto-approve
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Terraform apply failed" -ForegroundColor Red
    exit 1
}
Write-Host ""

Write-Host "Step 2: Preparing agent (creating new version)..." -ForegroundColor Yellow
$AGENT_ID = terraform output -raw bedrock_agent_id 2>$null
if ([string]::IsNullOrEmpty($AGENT_ID)) {
    Write-Host "ERROR: Could not get agent ID from terraform" -ForegroundColor Red
    exit 1
}

Write-Host "Agent ID: $AGENT_ID" -ForegroundColor Gray
aws bedrock-agent prepare-agent --agent-id $AGENT_ID --region us-east-1 --profile default
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Agent preparation failed" -ForegroundColor Red
    exit 1
}
Write-Host ""

Write-Host "Step 3: Waiting for agent to be ready..." -ForegroundColor Yellow
Start-Sleep -Seconds 30
Write-Host ""

Write-Host "========================================" -ForegroundColor Green
Write-Host "SUCCESS! Agent updated with new instructions" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Test the agent with a question about your PDFs"
Write-Host "2. Check CloudWatch logs for 'SEARCH ACTION CALLED'"
Write-Host "3. If search is still not called, you may need to:"
Write-Host "   - Create a new agent version in AWS Console"
Write-Host "   - Update the alias to point to the new version"
Write-Host ""
