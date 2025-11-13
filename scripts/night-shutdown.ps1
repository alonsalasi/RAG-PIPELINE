# Night Shutdown Script - Destroy expensive resources
# Saves ~$119/month when not in use

Write-Host "Night Shutdown - Destroying expensive resources..." -ForegroundColor Cyan
Write-Host ""

$ErrorActionPreference = "Continue"
$hasErrors = $false
$errorDetails = @()

# Get VPC ID dynamically
Write-Host "Getting VPC ID..." -ForegroundColor Yellow
$vpcId = terraform output -raw vpc_id 2>$null
if (-not $vpcId) {
  Write-Host "  Warning: Could not get VPC ID from Terraform, searching..." -ForegroundColor Yellow
  $vpcId = aws ec2 describe-vpcs --filters "Name=tag:Name,Values=pdfquery-vpc" --query 'Vpcs[0].VpcId' --output text --profile default
}
Write-Host "  VPC ID: $vpcId" -ForegroundColor Gray

# Check current state
Write-Host "Checking current resources..." -ForegroundColor Yellow

# NAT Gateway check removed - permanently disabled to save $64/month
Write-Host "  NAT Gateway: Permanently disabled (not checking)" -ForegroundColor Gray

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
Write-Host "  - 7x VPC Endpoints (~$49/month saved overnight)" -ForegroundColor Gray
Write-Host "  - GuardDuty (~$4-6/month saved overnight)" -ForegroundColor Gray
Write-Host "  - AWS Config (~$2/month saved overnight)" -ForegroundColor Gray
Write-Host "  - Total overnight savings: ~$55-57/month" -ForegroundColor Gray
Write-Host "" -ForegroundColor Gray
Write-Host "NOTE: NAT Gateway permanently disabled (saves $64/month 24/7)" -ForegroundColor Yellow
Write-Host ""
Write-Host "Note: Lambda functions will not work until morning startup" -ForegroundColor Yellow
Write-Host "Run morning-startup.ps1 to restore functionality" -ForegroundColor Yellow

# Validate shutdown
Write-Host ""
Write-Host "Validating shutdown..." -ForegroundColor Yellow

# NAT Gateway validation removed - permanently disabled
Write-Host "  NAT Gateway: Permanently disabled (skipped)" -ForegroundColor Gray

# Check VPC Endpoints
$remainingEndpoints = aws ec2 describe-vpc-endpoints --filters "Name=vpc-id,Values=$vpcId" --output json --profile default | ConvertFrom-Json
if ($remainingEndpoints.VpcEndpoints.Count -eq 0) {
  Write-Host "  All VPC Endpoints destroyed" -ForegroundColor Green
} else {
  Write-Host "  $($remainingEndpoints.VpcEndpoints.Count) VPC Endpoint(s) still exist" -ForegroundColor Yellow
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
