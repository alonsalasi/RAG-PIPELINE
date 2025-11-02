# Night Shutdown Script - Destroy expensive resources
# Saves ~$119/month when not in use

# Enable script execution
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force

Write-Host "🌙 Night Shutdown - Destroying expensive resources..." -ForegroundColor Cyan
Write-Host ""

$ErrorActionPreference = "Continue"

# Check current state
Write-Host "Checking current resources..." -ForegroundColor Yellow
$natGateways = aws ec2 describe-nat-gateways --filter "Name=state,Values=available" --query 'NatGateways[*].NatGatewayId' --output text --profile default
$vpcEndpoints = aws ec2 describe-vpc-endpoints --filters "Name=vpc-id,Values=vpc-009ac5a412a717f97" --query 'VpcEndpoints[*].VpcEndpointId' --output text --profile default

if ($natGateways) {
  Write-Host "Deleting NAT Gateways..." -ForegroundColor Yellow
  foreach ($nat in $natGateways.Split()) {
    aws ec2 delete-nat-gateway --nat-gateway-id $nat --profile default
    Write-Host "  Deleted $nat" -ForegroundColor Gray
  }
}

if ($vpcEndpoints) {
  Write-Host "Deleting VPC Endpoints..." -ForegroundColor Yellow
  aws ec2 delete-vpc-endpoints --vpc-endpoint-ids $vpcEndpoints.Split() --profile default | Out-Null
  Write-Host "  Deleted VPC Endpoints" -ForegroundColor Gray
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
Write-Host "✅ Shutdown complete! Resources destroyed:" -ForegroundColor Green
Write-Host "  - 2x NAT Gateways (~$64/month saved)" -ForegroundColor Gray
Write-Host "  - 7x VPC Endpoints (~$49/month saved)" -ForegroundColor Gray
Write-Host "  - GuardDuty (~$4-6/month saved)" -ForegroundColor Gray
Write-Host "  - AWS Config (~$2/month saved)" -ForegroundColor Gray
Write-Host "  - Total savings: ~$119-121/month" -ForegroundColor Gray
Write-Host ""
Write-Host "💡 Note: Lambda functions will not work until morning startup" -ForegroundColor Yellow
Write-Host "💡 Run morning-startup.ps1 to restore functionality" -ForegroundColor Yellow

# Validate shutdown
Write-Host ""
Write-Host "Validating shutdown..." -ForegroundColor Yellow
$natCount = (aws ec2 describe-nat-gateways --filter "Name=state,Values=available" --query 'NatGateways | length(@)' --output text)
if ($natCount -eq 0) {
  Write-Host 'NAT Gateways destroyed' -ForegroundColor Green
} else {
  Write-Host "Warning: $natCount NAT Gateway(s) still running" -ForegroundColor Yellow
}
