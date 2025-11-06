# Force update Bedrock Agent to use search function
# Run this after changing agent instructions

$ErrorActionPreference = "Stop"

Write-Host "=== Force Updating Bedrock Agent ===" -ForegroundColor Cyan

# Get agent ID from terraform output
$agentId = terraform output -raw bedrock_agent_id
$aliasId = terraform output -raw bedrock_agent_alias_id
$region = terraform output -raw aws_region

Write-Host "Agent ID: $agentId" -ForegroundColor Yellow
Write-Host "Alias ID: $aliasId" -ForegroundColor Yellow
Write-Host "Region: $region" -ForegroundColor Yellow

# Step 1: Prepare the agent (updates DRAFT version)
Write-Host "`nStep 1: Preparing agent (updating DRAFT)..." -ForegroundColor Green
aws bedrock-agent prepare-agent `
    --agent-id $agentId `
    --region $region `
    --no-verify-ssl

Start-Sleep -Seconds 10

# Step 2: Create a new version from DRAFT
Write-Host "`nStep 2: Creating new version from DRAFT..." -ForegroundColor Green
$versionResponse = aws bedrock-agent create-agent-version `
    --agent-id $agentId `
    --region $region `
    --no-verify-ssl

$version = ($versionResponse | ConvertFrom-Json).agentVersion.version
Write-Host "Created version: $version" -ForegroundColor Yellow

Start-Sleep -Seconds 10

# Step 3: Update alias to point to new version
Write-Host "`nStep 3: Updating alias to point to version $version..." -ForegroundColor Green
aws bedrock-agent update-agent-alias `
    --agent-id $agentId `
    --agent-alias-id $aliasId `
    --agent-alias-name "production" `
    --routing-configuration "agentVersion=$version" `
    --region $region `
    --no-verify-ssl

Write-Host "`n=== Agent Updated Successfully ===" -ForegroundColor Green
Write-Host "The agent will now call search_documents for every query." -ForegroundColor Cyan
Write-Host "`nTest with: 'Show me the Chery car in red'" -ForegroundColor Yellow
