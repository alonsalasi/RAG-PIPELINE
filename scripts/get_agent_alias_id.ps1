# Script to get the Bedrock Agent Alias ID for the production alias
# Run this after terraform apply to get the actual alias ID

param(
    [Parameter(Mandatory=$false)]
    [string]$Profile = "default"
)

Write-Host "Fetching Bedrock Agent Alias ID..." -ForegroundColor Cyan

# Get the agent ID from Terraform output or state
$agentId = terraform output -raw bedrock_agent_id 2>$null

if (-not $agentId) {
    Write-Host "Could not get agent ID from Terraform output. Trying state..." -ForegroundColor Yellow
    $agentId = (terraform state show aws_bedrockagent_agent.rag_agent | Select-String "agent_id\s+=\s+(.+)" | ForEach-Object { $_.Matches.Groups[1].Value }).Trim('"')
}

if (-not $agentId) {
    Write-Host "ERROR: Could not find agent ID. Make sure Terraform has been applied." -ForegroundColor Red
    exit 1
}

Write-Host "Agent ID: $agentId" -ForegroundColor Green

# List aliases and find production
$aliases = aws bedrock-agent list-agent-aliases --agent-id $agentId --profile $Profile | ConvertFrom-Json

$prodAlias = $aliases.agentAliasSummaries | Where-Object { $_.agentAliasName -eq 'production' }

if ($prodAlias) {
    Write-Host "`nProduction Alias ID: $($prodAlias.agentAliasId)" -ForegroundColor Green
    Write-Host "`nUpdate Lambda_agent.tf with this value:" -ForegroundColor Cyan
    Write-Host "BEDROCK_AGENT_ALIAS_ID = `"$($prodAlias.agentAliasId)`"" -ForegroundColor Yellow
} else {
    Write-Host "ERROR: Production alias not found. Make sure the agent has been prepared." -ForegroundColor Red
    exit 1
}
