# Night Shutdown Script - Destroy expensive resources
# Saves ~$119/month when not in use

Write-Host "Night Shutdown - Destroying expensive resources..." -ForegroundColor Cyan
Write-Host ""

$ErrorActionPreference = "Continue"

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

# Get NAT Gateways (check all active states)
$natGatewaysJson = aws ec2 describe-nat-gateways --filter "Name=vpc-id,Values=$vpcId" "Name=state,Values=available,pending" --output json --profile default | ConvertFrom-Json
$natGateways = $natGatewaysJson.NatGateways

if ($natGateways -and $natGateways.Count -gt 0) {
  Write-Host "Found $($natGateways.Count) NAT Gateway(s) to delete" -ForegroundColor Yellow
  foreach ($nat in $natGateways) {
    Write-Host "  Deleting NAT Gateway: $($nat.NatGatewayId) (State: $($nat.State))" -ForegroundColor Gray
    try {
      aws ec2 delete-nat-gateway --nat-gateway-id $nat.NatGatewayId --profile default 2>&1 | Out-Null
      Write-Host "    Deletion initiated" -ForegroundColor Green
    } catch {
      Write-Host "    Failed: $_" -ForegroundColor Red
    }
  }
  
  # Wait for NAT Gateways to start deleting
  Write-Host "  Waiting for NAT Gateways to begin deletion (10s)..." -ForegroundColor Gray
  Start-Sleep -Seconds 10
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
Write-Host "  - 2x NAT Gateways (~$64/month saved)" -ForegroundColor Gray
Write-Host "  - 7x VPC Endpoints (~$49/month saved)" -ForegroundColor Gray
Write-Host "  - GuardDuty (~$4-6/month saved)" -ForegroundColor Gray
Write-Host "  - AWS Config (~$2/month saved)" -ForegroundColor Gray
Write-Host "  - Total savings: ~$119-121/month" -ForegroundColor Gray
Write-Host ""
Write-Host "Note: Lambda functions will not work until morning startup" -ForegroundColor Yellow
Write-Host "Run morning-startup.ps1 to restore functionality" -ForegroundColor Yellow

# Validate shutdown
Write-Host ""
Write-Host "Validating shutdown..." -ForegroundColor Yellow

# Check NAT Gateways (including deleting state)
$remainingNats = aws ec2 describe-nat-gateways --filter "Name=vpc-id,Values=$vpcId" "Name=state,Values=available,pending,deleting" --output json --profile default | ConvertFrom-Json
if ($remainingNats.NatGateways.Count -eq 0) {
  Write-Host "  All NAT Gateways destroyed" -ForegroundColor Green
} else {
  Write-Host "  $($remainingNats.NatGateways.Count) NAT Gateway(s) in deletion (this is normal, takes ~2 minutes)" -ForegroundColor Yellow
  foreach ($nat in $remainingNats.NatGateways) {
    Write-Host "    - $($nat.NatGatewayId): $($nat.State)" -ForegroundColor Gray
  }
}

# Check VPC Endpoints
$remainingEndpoints = aws ec2 describe-vpc-endpoints --filters "Name=vpc-id,Values=$vpcId" --output json --profile default | ConvertFrom-Json
if ($remainingEndpoints.VpcEndpoints.Count -eq 0) {
  Write-Host "  All VPC Endpoints destroyed" -ForegroundColor Green
} else {
  Write-Host "  $($remainingEndpoints.VpcEndpoints.Count) VPC Endpoint(s) still exist" -ForegroundColor Yellow
}
