# Security Validation Script for LEIDOS Project
# This script validates security configurations and checks for common issues

param(
    [switch]$Fix,
    [switch]$Verbose
)

Write-Host "=== LEIDOS Project Security Validation ===" -ForegroundColor Green

$ErrorCount = 0
$WarningCount = 0

function Write-SecurityCheck {
    param($Message, $Status, $Details = "")
    
    $color = switch ($Status) {
        "PASS" { "Green" }
        "FAIL" { "Red" }
        "WARN" { "Yellow" }
        default { "White" }
    }
    
    Write-Host "[$Status] $Message" -ForegroundColor $color
    if ($Details -and $Verbose) {
        Write-Host "    $Details" -ForegroundColor Gray
    }
    
    if ($Status -eq "FAIL") { $script:ErrorCount++ }
    if ($Status -eq "WARN") { $script:WarningCount++ }
}

# Check 1: Environment Variables Configuration
Write-Host "`n1. Environment Variables Security" -ForegroundColor Cyan

$requiredEnvVars = @(
    "S3_BUCKET",
    "AWS_REGION", 
    "BEDROCK_AGENT_ID",
    "BEDROCK_AGENT_ALIAS_ID",
    "SES_SENDER_EMAIL"
)

foreach ($envVar in $requiredEnvVars) {
    if ([string]::IsNullOrEmpty([Environment]::GetEnvironmentVariable($envVar))) {
        Write-SecurityCheck "Environment variable $envVar is not set" "WARN" "Should be configured in Lambda environment"
    } else {
        Write-SecurityCheck "Environment variable $envVar is configured" "PASS"
    }
}

# Check 2: Terraform Files Security
Write-Host "`n2. Terraform Configuration Security" -ForegroundColor Cyan

$terraformFiles = Get-ChildItem -Path "." -Filter "*.tf" -ErrorAction SilentlyContinue

foreach ($file in $terraformFiles) {
    $content = Get-Content $file.FullName -Raw -ErrorAction SilentlyContinue
    
    if ($content) {
        # Check for hardcoded secrets
        if ($content -match '(password|secret|key)\s*=\s*"[^"]*"' -and $content -notmatch 'aws_secretsmanager_secret') {
            Write-SecurityCheck "Potential hardcoded secret in $($file.Name)" "FAIL" "Use AWS Secrets Manager instead"
        }
        
        # Check for overly permissive IAM policies
        if ($content -match '"Resource"\s*:\s*"\*"' -and $content -match '"Action"\s*:\s*\[.*"s3:.*"') {
            Write-SecurityCheck "Overly permissive S3 policy in $($file.Name)" "WARN" "Consider restricting to specific buckets"
        }
        
        # Check for missing encryption
        if ($content -match 'aws_s3_bucket"' -and $content -notmatch 'server_side_encryption') {
            Write-SecurityCheck "S3 bucket without encryption in $($file.Name)" "FAIL" "Enable server-side encryption"
        }
        
        Write-SecurityCheck "Terraform file $($file.Name) security review" "PASS"
    }
}

# Check 3: Python Files Security
Write-Host "`n3. Python Code Security" -ForegroundColor Cyan

$pythonFiles = Get-ChildItem -Path "." -Filter "*.py" -Recurse -ErrorAction SilentlyContinue

foreach ($file in $pythonFiles) {
    $content = Get-Content $file.FullName -Raw -ErrorAction SilentlyContinue
    
    if ($content) {
        # Check for hardcoded credentials
        if ($content -match '(password|secret|key|token)\s*=\s*["\'][^"\']*["\']' -and $content -notmatch 'os\.getenv|os\.environ') {
            Write-SecurityCheck "Potential hardcoded credential in $($file.Name)" "FAIL" "Use environment variables or AWS Secrets Manager"
        }
        
        # Check for SQL injection vulnerabilities
        if ($content -match 'execute\s*\(\s*["\'].*%.*["\']' -or $content -match 'query\s*\(\s*["\'].*\+.*["\']') {
            Write-SecurityCheck "Potential SQL injection in $($file.Name)" "FAIL" "Use parameterized queries"
        }
        
        # Check for path traversal vulnerabilities
        if ($content -match 'open\s*\(\s*.*\+.*\)' -and $content -notmatch 'os\.path\.join|pathlib') {
            Write-SecurityCheck "Potential path traversal in $($file.Name)" "WARN" "Use os.path.join() for file paths"
        }
        
        # Check for logging of sensitive data
        if ($content -match 'log.*\(.*password|log.*\(.*secret|log.*\(.*key') {
            Write-SecurityCheck "Potential sensitive data logging in $($file.Name)" "WARN" "Sanitize logged data"
        }
        
        Write-SecurityCheck "Python file $($file.Name) security review" "PASS"
    }
}

# Check 4: Docker Files Security
Write-Host "`n4. Docker Configuration Security" -ForegroundColor Cyan

$dockerFiles = Get-ChildItem -Path "." -Filter "*Dockerfile*" -Recurse -ErrorAction SilentlyContinue

foreach ($file in $dockerFiles) {
    $content = Get-Content $file.FullName -Raw -ErrorAction SilentlyContinue
    
    if ($content) {
        # Check for running as root
        if ($content -notmatch 'USER\s+\w+' -or $content -match 'USER\s+root') {
            Write-SecurityCheck "Docker container may run as root in $($file.Name)" "WARN" "Consider using non-root user"
        }
        
        # Check for hardcoded secrets
        if ($content -match 'ENV\s+.*(?:PASSWORD|SECRET|KEY|TOKEN)=') {
            Write-SecurityCheck "Potential hardcoded secret in $($file.Name)" "FAIL" "Use runtime environment variables"
        }
        
        Write-SecurityCheck "Docker file $($file.Name) security review" "PASS"
    }
}

# Check 5: Network Security
Write-Host "`n5. Network Security Configuration" -ForegroundColor Cyan

# Check VPC configuration
if (Test-Path "VPC.tf") {
    $vpcContent = Get-Content "VPC.tf" -Raw
    
    if ($vpcContent -match 'cidr_block.*=.*"0\.0\.0\.0/0"') {
        Write-SecurityCheck "Overly permissive CIDR block in VPC" "FAIL" "Use more restrictive CIDR blocks"
    } else {
        Write-SecurityCheck "VPC CIDR configuration" "PASS"
    }
    
    if ($vpcContent -match 'aws_security_group_rule.*cidr_blocks.*=.*\["0\.0\.0\.0/0"\]') {
        Write-SecurityCheck "Security group allows all traffic" "WARN" "Restrict to necessary IP ranges"
    } else {
        Write-SecurityCheck "Security group configuration" "PASS"
    }
}

# Summary
Write-Host "`n=== Security Validation Summary ===" -ForegroundColor Green
Write-Host "Errors: $ErrorCount" -ForegroundColor $(if ($ErrorCount -gt 0) { "Red" } else { "Green" })
Write-Host "Warnings: $WarningCount" -ForegroundColor $(if ($WarningCount -gt 0) { "Yellow" } else { "Green" })

if ($ErrorCount -eq 0 -and $WarningCount -eq 0) {
    Write-Host "✅ All security checks passed!" -ForegroundColor Green
    exit 0
} elseif ($ErrorCount -eq 0) {
    Write-Host "⚠️  Security validation completed with warnings" -ForegroundColor Yellow
    exit 0
} else {
    Write-Host "❌ Security validation failed with errors" -ForegroundColor Red
    exit 1
}