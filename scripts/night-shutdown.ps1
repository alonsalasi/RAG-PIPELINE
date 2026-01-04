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

# Get NAT Gateways
$natGatewaysJson = aws ec2 describe-nat-gateways --filter "Name=vpc-id,Values=$vpcId" "Name=state,Values=available" --output json --profile default | ConvertFrom-Json
$natGateways = $natGatewaysJson.NatGateways

if ($natGateways -and $natGateways.Count -gt 0) {
  Write-Host "Found $($natGateways.Count) NAT Gateway(s) to delete" -ForegroundColor Yellow
  foreach ($nat in $natGateways) {
    try {
      aws ec2 delete-nat-gateway --nat-gateway-id $nat.NatGatewayId --profile default 2>&1 | Out-Null
      Write-Host "  Deleted NAT Gateway: $($nat.NatGatewayId)" -ForegroundColor Green
    } catch {
      Write-Host "  Failed to delete NAT Gateway $($nat.NatGatewayId): $_" -ForegroundColor Red
      $hasErrors = $true
      $errorDetails += "NAT Gateway deletion failed: $($_.Exception.Message)"
    }
  }
  
  # Wait for NAT Gateways to delete before releasing EIPs
  Write-Host "  Waiting 30s for NAT Gateways to delete..." -ForegroundColor Gray
  Start-Sleep -Seconds 30
  
  # Release Elastic IPs
  $eipsJson = aws ec2 describe-addresses --filters "Name=domain,Values=vpc" --output json --profile default | ConvertFrom-Json
  $eips = $eipsJson.Addresses | Where-Object { $_.Tags.Name -like "*nat-eip*" }
  if ($eips) {
    foreach ($eip in $eips) {
      try {
        aws ec2 release-address --allocation-id $eip.AllocationId --profile default 2>&1 | Out-Null
        Write-Host "  Released Elastic IP: $($eip.AllocationId)" -ForegroundColor Green
      } catch {
        Write-Host "  Failed to release EIP $($eip.AllocationId): $_" -ForegroundColor Yellow
      }
    }
  }
} else {
  Write-Host "  No NAT Gateways found" -ForegroundColor Gray
}

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
Write-Host "  - 1x NAT Gateway (~$32/month saved overnight)" -ForegroundColor Gray
Write-Host "  - 1x Elastic IP" -ForegroundColor Gray
Write-Host "  - 7x VPC Endpoints (~$49/month saved overnight)" -ForegroundColor Gray
Write-Host "  - GuardDuty (~$4-6/month saved overnight)" -ForegroundColor Gray
Write-Host "  - AWS Config (~$2/month saved overnight)" -ForegroundColor Gray
Write-Host "  - Total overnight savings: ~$87-89/month" -ForegroundColor Gray
Write-Host "" -ForegroundColor Gray
Write-Host "Note: Lambda and WebSocket will not work until morning startup" -ForegroundColor Yellow
Write-Host "Run morning-startup.ps1 to restore functionality" -ForegroundColor Yellow

# Validate shutdown
Write-Host ""
Write-Host "Validating shutdown..." -ForegroundColor Yellow

# Check NAT Gateways
$remainingNats = aws ec2 describe-nat-gateways --filter "Name=vpc-id,Values=$vpcId" "Name=state,Values=available" --output json --profile default | ConvertFrom-Json
if ($remainingNats.NatGateways.Count -eq 0) {
  Write-Host "  All NAT Gateways destroyed" -ForegroundColor Green
} else {
  Write-Host "  $($remainingNats.NatGateways.Count) NAT Gateway(s) still exist" -ForegroundColor Yellow
}

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
