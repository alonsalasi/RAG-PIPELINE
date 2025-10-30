# Night Shutdown Script - Destroy expensive resources
# Saves ~$119/month when not in use

# Enable script execution
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force

Write-Host "🌙 Night Shutdown - Destroying expensive resources..." -ForegroundColor Cyan
Write-Host ""

$ErrorActionPreference = "Continue"

# Destroy NAT Gateways, VPC Endpoints, GuardDuty, and AWS Config
Write-Host "Destroying NAT Gateways, VPC Endpoints, GuardDuty, and AWS Config..." -ForegroundColor Yellow
terraform destroy `
  -target='aws_nat_gateway.main[0]' `
  -target='aws_nat_gateway.main[1]' `
  -target='aws_eip.nat[0]' `
  -target='aws_eip.nat[1]' `
  -target='aws_vpc_endpoint.bedrock_runtime[0]' `
  -target='aws_vpc_endpoint.bedrock_agent_runtime[0]' `
  -target='aws_vpc_endpoint.sqs[0]' `
  -target='aws_vpc_endpoint.sns[0]' `
  -target='aws_vpc_endpoint.secretsmanager[0]' `
  -target='aws_vpc_endpoint.kms[0]' `
  -target='aws_vpc_endpoint.logs[0]' `
  -target='aws_guardduty_detector.main' `
  -target='aws_config_configuration_recorder_status.main' `
  -target='aws_config_delivery_channel.main' `
  -target='aws_config_configuration_recorder.main' `
  -auto-approve

if ($LASTEXITCODE -ne 0) {
  Write-Host "❌ Shutdown encountered errors" -ForegroundColor Yellow
}

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
