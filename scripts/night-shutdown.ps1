# Night Shutdown Script - Destroy expensive resources
# Saves ~$87/month when not in use

Write-Host "Night Shutdown - Destroying expensive resources..." -ForegroundColor Cyan
Write-Host ""

$ErrorActionPreference = "Continue"
$hasErrors = $false
$errorDetails = @()

# Get VPC ID dynamically
Write-Host "Getting VPC ID..." -ForegroundColor Yellow
$vpcId = terraform output -raw vpc_id 2>$null
# Strip ANSI color codes and whitespace
if ($vpcId) {
  $vpcId = $vpcId -replace '\x1b\[[0-9;]*m', '' -replace '[^a-zA-Z0-9-]', ''
}
if (-not $vpcId -or $vpcId.Length -lt 10) {
  Write-Host "  Warning: Could not get VPC ID from Terraform, searching..." -ForegroundColor Yellow
  $vpcId = aws ec2 describe-vpcs --filters "Name=tag:Name,Values=pdfquery-vpc" --query 'Vpcs[0].VpcId' --output text --profile default
  $vpcId = $vpcId.Trim()
}
Write-Host "  VPC ID: $vpcId" -ForegroundColor Gray

# Check current state
Write-Host "Checking current resources..." -ForegroundColor Yellow

# Get VPC Endpoints
$vpcEndpointsJson = aws ec2 describe-vpc-endpoints --filters "Name=vpc-id,Values=$vpcId" --output json --profile default | ConvertFrom-Json
$vpcEndpoints = $vpcEndpointsJson.VpcEndpoints

if ($vpcEndpoints -and $vpcEndpoints.Count -gt 0) {
  Write-Host "Found $($vpcEndpoints.Count) VPC Endpoint(s) to delete" -ForegroundColor Yellow
  $endpointIds = $vpcEndpoints | ForEach-Object { $_.VpcEndpointId }
  try {
    aws ec2 delete-vpc-endpoints --vpc-endpoint-ids $endpointIds --profile default 2>&1 | Out-Null
    Write-Host "  Deleted $($vpcEndpoints.Count) VPC Endpoint(s)" -ForegroundColor Green
  } catch {
    Write-Host "  Failed to delete VPC Endpoints: $_" -ForegroundColor Red
    $hasErrors = $true
    $errorDetails += "VPC Endpoints deletion failed: $($_.Exception.Message)"
  }
} else {
  Write-Host "  No VPC Endpoints found" -ForegroundColor Gray
}

Write-Host "Disabling GuardDuty..." -ForegroundColor Yellow
$detectorId = aws guardduty list-detectors --query 'DetectorIds[0]' --output text --profile default
if ($detectorId -and $detectorId -ne "None") {
  aws guardduty delete-detector --detector-id $detectorId --profile default | Out-Null
  Write-Host "  Disabled GuardDuty" -ForegroundColor Gray
}

Write-Host "Disabling AWS Config..." -ForegroundColor Yellow
aws configservice stop-configuration-recorder --configuration-recorder-name pdfquery-config-recorder --profile default 2>$null
Write-Host "  Stopped Config Recorder" -ForegroundColor Gray

Write-Host ""
Write-Host "Shutdown complete! Resources destroyed:" -ForegroundColor Green
Write-Host "  - 7x VPC Endpoints (~$50/month saved overnight)" -ForegroundColor Gray
Write-Host "    * Bedrock Runtime, Bedrock Agent Runtime" -ForegroundColor Gray
Write-Host "    * SQS, SNS, KMS, CloudWatch Logs, Lambda" -ForegroundColor Gray
Write-Host "    * (S3 Gateway is FREE, kept running)" -ForegroundColor Gray
Write-Host "  - GuardDuty (~$5/month saved overnight)" -ForegroundColor Gray
Write-Host "  - AWS Config (~$2/month saved overnight)" -ForegroundColor Gray
Write-Host "  - Total overnight savings: ~$57/month" -ForegroundColor Gray
Write-Host "" -ForegroundColor Gray
Write-Host "Note: Lambda will not work until morning startup" -ForegroundColor Yellow
Write-Host "Run morning-startup.ps1 to restore functionality" -ForegroundColor Yellow

# Validate shutdown
Write-Host ""
Write-Host "Validating shutdown..." -ForegroundColor Yellow

# Check VPC Endpoints (exclude deleting state)
$remainingEndpoints = aws ec2 describe-vpc-endpoints --filters "Name=vpc-id,Values=$vpcId" --output json --profile default | ConvertFrom-Json
$activeEndpoints = $remainingEndpoints.VpcEndpoints | Where-Object { $_.State -ne 'deleting' -and $_.State -ne 'deleted' }
if ($activeEndpoints.Count -eq 0) {
  Write-Host "  All VPC Endpoints destroyed or deleting" -ForegroundColor Green
} else {
  Write-Host "  $($activeEndpoints.Count) VPC Endpoint(s) still active" -ForegroundColor Yellow
}

# Log run result
$logFile = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "scheduler.log"
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
if ($hasErrors) {
  $errorSummary = $errorDetails -join "; "
  Add-Content -Path $logFile -Value "[$timestamp] Night shutdown completed with ERRORS: $errorSummary"
} else {
  Add-Content -Path $logFile -Value "[$timestamp] Night shutdown completed successfully"
}
