# Morning Startup Script - Recreate expensive resources
# Restores full functionality

# Enable script execution
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force

Write-Host "Morning Startup - Recreating infrastructure..." -ForegroundColor Cyan
Write-Host ""

$ErrorActionPreference = "Stop"

# CRITICAL: Change to Terraform directory
$terraformDir = "D:\Projects\LEIDOS"
Set-Location $terraformDir
Write-Host "Working directory: $terraformDir" -ForegroundColor Gray

# Initialize Terraform backend
Write-Host "Initializing Terraform..." -ForegroundColor Yellow
terraform init -reconfigure

if ($LASTEXITCODE -ne 0) {
  Write-Host "Terraform init failed" -ForegroundColor Red
  $logFile = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "scheduler.log"
  $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  Add-Content -Path $logFile -Value "[$timestamp] Morning startup FAILED - Terraform init returned exit code $LASTEXITCODE"
  exit 1
}

# Recreate NAT Gateway, VPC Endpoints, GuardDuty, and AWS Config
Write-Host "Creating NAT Gateway, VPC Endpoints, GuardDuty, and AWS Config..." -ForegroundColor Yellow
terraform apply `
  -target='aws_eip.nat[0]' `
  -target='aws_nat_gateway.main[0]' `
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
  Write-Host "Startup failed" -ForegroundColor Red
  $logFile = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "scheduler.log"
  $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  Add-Content -Path $logFile -Value "[$timestamp] Morning startup FAILED - Terraform apply returned exit code $LASTEXITCODE"
  exit 1
}

Write-Host ""
Write-Host "Startup complete! Resources recreated:" -ForegroundColor Green
Write-Host "  - 1x NAT Gateway ($32/month)" -ForegroundColor Gray
Write-Host "  - 1x Elastic IP" -ForegroundColor Gray
Write-Host "  - 2x Private Route Tables" -ForegroundColor Gray
Write-Host "  - 8x VPC Endpoints (7 interface + 1 gateway)" -ForegroundColor Gray
Write-Host "  - GuardDuty" -ForegroundColor Gray
Write-Host "  - AWS Config" -ForegroundColor Gray
Write-Host "" -ForegroundColor Gray
Write-Host "System is now fully operational" -ForegroundColor Green
Write-Host "WebSocket and Lambda functions have full internet access" -ForegroundColor Green

# Log successful run
$logFile = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "scheduler.log"
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path $logFile -Value "[$timestamp] Morning startup completed successfully"
