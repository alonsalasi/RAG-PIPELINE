# Morning Startup Script - Recreate expensive resources
# Restores full functionality

# Enable script execution
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force

Write-Host "☀️ Morning Startup - Recreating infrastructure..." -ForegroundColor Cyan
Write-Host ""

$ErrorActionPreference = "Stop"

# Recreate NAT Gateways, Route Tables, VPC Endpoints, GuardDuty, and AWS Config
Write-Host "Creating NAT Gateways, Route Tables, VPC Endpoints, GuardDuty, and AWS Config..." -ForegroundColor Yellow
terraform apply `
  -target='aws_eip.nat[0]' `
  -target='aws_eip.nat[1]' `
  -target='aws_nat_gateway.main[0]' `
  -target='aws_nat_gateway.main[1]' `
  -target='aws_route_table.private[0]' `
  -target='aws_route_table.private[1]' `
  -target='aws_route_table_association.private[0]' `
  -target='aws_route_table_association.private[1]' `
  -target='aws_vpc_endpoint.s3_gateway[0]' `
  -target='aws_vpc_endpoint.bedrock_runtime[0]' `
  -target='aws_vpc_endpoint.bedrock_agent_runtime[0]' `
  -target='aws_vpc_endpoint.sqs[0]' `
  -target='aws_vpc_endpoint.sns[0]' `
  -target='aws_vpc_endpoint.secretsmanager[0]' `
  -target='aws_vpc_endpoint.kms[0]' `
  -target='aws_vpc_endpoint.logs[0]' `
  -target='aws_guardduty_detector.main' `
  -target='aws_config_configuration_recorder.main' `
  -target='aws_config_delivery_channel.main' `
  -target='aws_config_configuration_recorder_status.main' `
  -auto-approve

if ($LASTEXITCODE -ne 0) {
  Write-Host "❌ Startup failed" -ForegroundColor Red
  exit 1
}

Write-Host ""
Write-Host "✅ Startup complete! Resources recreated:" -ForegroundColor Green
Write-Host "  - 2x NAT Gateways" -ForegroundColor Gray
Write-Host "  - 2x Private Route Tables" -ForegroundColor Gray
Write-Host "  - 8x VPC Endpoints (7 interface + 1 gateway)" -ForegroundColor Gray
Write-Host "  - GuardDuty" -ForegroundColor Gray
Write-Host "  - AWS Config" -ForegroundColor Gray

# Validate resources are running
Write-Host ""
Write-Host "Validating resources..." -ForegroundColor Yellow
$natCount = (aws ec2 describe-nat-gateways --filter "Name=state,Values=available" --query 'NatGateways | length(@)' --output text)
if ($natCount -ge 2) {
  Write-Host "✓ NAT Gateways operational" -ForegroundColor Green
} else {
  Write-Host "⚠ NAT Gateways may not be ready" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "💡 System is now fully operational" -ForegroundColor Green
Write-Host "💡 Lambda functions can access AWS services" -ForegroundColor Green
