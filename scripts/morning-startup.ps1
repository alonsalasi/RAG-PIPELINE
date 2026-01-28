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

# Recreate VPC Endpoints, GuardDuty, and AWS Config
Write-Host "Creating VPC Endpoints, GuardDuty, and AWS Config..." -ForegroundColor Yellow
terraform apply `
  -target='aws_vpc_endpoint.s3_gateway[0]' `
  -target='aws_vpc_endpoint.bedrock_runtime[0]' `
  -target='aws_vpc_endpoint.bedrock_agent_runtime[0]' `
  -target='aws_vpc_endpoint.sqs[0]' `
  -target='aws_vpc_endpoint.sns[0]' `
  -target='aws_vpc_endpoint.kms[0]' `
  -target='aws_vpc_endpoint.logs[0]' `
  -target='aws_vpc_endpoint.lambda[0]' `
  -target='aws_guardduty_detector.main' `
  -target='aws_guardduty_detector_feature.s3_protection' `
  -target='aws_guardduty_detector_feature.ebs_malware_protection' `
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
Write-Host "  - 8x VPC Endpoints (7 interface + 1 gateway)" -ForegroundColor Gray
Write-Host "    * S3 Gateway (FREE)" -ForegroundColor Gray
Write-Host "    * Bedrock Runtime, Bedrock Agent Runtime" -ForegroundColor Gray
Write-Host "    * SQS, SNS, KMS, CloudWatch Logs, Lambda" -ForegroundColor Gray
Write-Host "  - GuardDuty (with S3 & EBS protection)" -ForegroundColor Gray
Write-Host "  - AWS Config" -ForegroundColor Gray
Write-Host "" -ForegroundColor Gray
Write-Host "System is now fully operational" -ForegroundColor Green
Write-Host "Lambda functions have access to all AWS services via VPC endpoints" -ForegroundColor Green

# Log successful run
$logFile = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "scheduler.log"
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path $logFile -Value "[$timestamp] Morning startup completed successfully"
