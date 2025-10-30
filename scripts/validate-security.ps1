# Security Validation Script for Windows PowerShell
# Run after deployment to verify security controls

Write-Host "=== Security Validation Script ===" -ForegroundColor Cyan
Write-Host ""

$project_name = "pdfquery"
$region = "us-east-1"
$errors = 0

# Function to check and report
function Test-SecurityControl {
    param(
        [string]$Name,
        [scriptblock]$Test,
        [string]$SuccessMessage,
        [string]$FailureMessage
    )
    
    Write-Host "Checking: $Name..." -NoNewline
    try {
        $result = & $Test
        if ($result) {
            Write-Host " ✓ PASS" -ForegroundColor Green
            Write-Host "  $SuccessMessage" -ForegroundColor Gray
            return $true
        } else {
            Write-Host " ✗ FAIL" -ForegroundColor Red
            Write-Host "  $FailureMessage" -ForegroundColor Yellow
            $script:errors++
            return $false
        }
    } catch {
        Write-Host " ✗ ERROR" -ForegroundColor Red
        $errorType = $_.Exception.GetType().Name
        Write-Host "  Error type: $errorType" -ForegroundColor Yellow
        $script:errors++
        return $false
    }
}

Write-Host "1. S3 Bucket Security" -ForegroundColor Yellow
Write-Host "-------------------" -ForegroundColor Yellow

# Check S3 encryption
Test-SecurityControl `
    -Name "S3 Bucket Encryption" `
    -Test {
        $bucketName = "$project_name-rag-documents-production"
        if (-not $bucketName -or $bucketName.Length -eq 0) {
            throw "Invalid bucket name"
        }
        $encryption = aws s3api get-bucket-encryption --bucket $bucketName 2>$null
        return $encryption -match "aws:kms"
    } `
    -SuccessMessage "S3 bucket is encrypted with KMS" `
    -FailureMessage "S3 bucket encryption not configured"

# Check S3 public access block
Test-SecurityControl `
    -Name "S3 Public Access Block" `
    -Test {
        $bucketName = "$project_name-rag-documents-production"
        if (-not $bucketName -or $bucketName.Length -eq 0) {
            throw "Invalid bucket name"
        }
        $block = aws s3api get-public-access-block --bucket $bucketName 2>$null | ConvertFrom-Json
        return $block.PublicAccessBlockConfiguration.BlockPublicAcls -eq $true
    } `
    -SuccessMessage "S3 bucket blocks public access" `
    -FailureMessage "S3 bucket may allow public access"

# Check S3 versioning
Test-SecurityControl `
    -Name "S3 Versioning" `
    -Test {
        $bucketName = "$project_name-rag-documents-production"
        if (-not $bucketName -or $bucketName.Length -eq 0) {
            throw "Invalid bucket name"
        }
        $versioning = aws s3api get-bucket-versioning --bucket $bucketName 2>$null
        return $versioning -match "Enabled"
    } `
    -SuccessMessage "S3 versioning is enabled" `
    -FailureMessage "S3 versioning is not enabled"

Write-Host ""
Write-Host "2. CloudTrail Logging" -ForegroundColor Yellow
Write-Host "-------------------" -ForegroundColor Yellow

Test-SecurityControl `
    -Name "CloudTrail Status" `
    -Test {
        $trail = aws cloudtrail get-trail-status --name "$project_name-agent-audit-trail" --region $region 2>$null | ConvertFrom-Json
        return $trail.IsLogging -eq $true
    } `
    -SuccessMessage "CloudTrail is actively logging" `
    -FailureMessage "CloudTrail is not logging"

Write-Host ""
Write-Host "3. GuardDuty Threat Detection" -ForegroundColor Yellow
Write-Host "----------------------------" -ForegroundColor Yellow

Test-SecurityControl `
    -Name "GuardDuty Status" `
    -Test {
        $detectors = aws guardduty list-detectors --region $region 2>$null | ConvertFrom-Json
        return $detectors.DetectorIds.Count -gt 0
    } `
    -SuccessMessage "GuardDuty is enabled" `
    -FailureMessage "GuardDuty is not enabled"

Write-Host ""
Write-Host "4. WAF Protection" -ForegroundColor Yellow
Write-Host "---------------" -ForegroundColor Yellow

Test-SecurityControl `
    -Name "WAF Web ACL" `
    -Test {
        $waf = aws wafv2 list-web-acls --scope REGIONAL --region $region 2>$null | ConvertFrom-Json
        return $waf.WebACLs.Count -gt 0
    } `
    -SuccessMessage "WAF is configured" `
    -FailureMessage "WAF is not configured"

Write-Host ""
Write-Host "5. Lambda Security" -ForegroundColor Yellow
Write-Host "----------------" -ForegroundColor Yellow

Test-SecurityControl `
    -Name "Lambda KMS Encryption" `
    -Test {
        $lambda = aws lambda get-function-configuration --function-name "$project_name-ingestion-worker" --region $region 2>$null | ConvertFrom-Json
        return $lambda.KMSKeyArn -ne $null
    } `
    -SuccessMessage "Lambda environment variables are encrypted" `
    -FailureMessage "Lambda encryption not configured"

Test-SecurityControl `
    -Name "Lambda X-Ray Tracing" `
    -Test {
        $lambda = aws lambda get-function-configuration --function-name "$project_name-ingestion-worker" --region $region 2>$null | ConvertFrom-Json
        return $lambda.TracingConfig.Mode -eq "Active"
    } `
    -SuccessMessage "X-Ray tracing is enabled" `
    -FailureMessage "X-Ray tracing is not enabled"

Test-SecurityControl `
    -Name "Lambda Timeout Configuration" `
    -Test {
        $lambda = aws lambda get-function-configuration --function-name "$project_name-ingestion-worker" --region $region 2>$null | ConvertFrom-Json
        return $lambda.Timeout -le 900
    } `
    -SuccessMessage "Lambda timeout properly configured" `
    -FailureMessage "Lambda timeout exceeds recommended limit"

Test-SecurityControl `
    -Name "API Gateway Throttling" `
    -Test {
        $stage = aws apigatewayv2 get-stage --api-id (aws apigatewayv2 get-apis --query "Items[?Name=='$project_name-api-gw'].ApiId" --output text) --stage-name production --region $region 2>$null | ConvertFrom-Json
        return $stage.DefaultRouteSettings.ThrottlingBurstLimit -gt 0
    } `
    -SuccessMessage "API Gateway throttling configured" `
    -FailureMessage "API Gateway throttling not configured"

Test-SecurityControl `
    -Name "Lambda Dead Letter Queue" `
    -Test {
        $lambda = aws lambda get-function-configuration --function-name "$project_name-ingestion-worker" --region $region 2>$null | ConvertFrom-Json
        return $lambda.DeadLetterConfig.TargetArn -ne $null
    } `
    -SuccessMessage "Dead Letter Queue is configured" `
    -FailureMessage "Dead Letter Queue is not configured"

Write-Host ""
Write-Host "6. Cognito Authentication" -ForegroundColor Yellow
Write-Host "-----------------------" -ForegroundColor Yellow

Test-SecurityControl `
    -Name "Cognito User Pool" `
    -Test {
        $pools = aws cognito-idp list-user-pools --max-results 10 --region $region 2>$null | ConvertFrom-Json
        return $pools.UserPools.Count -gt 0
    } `
    -SuccessMessage "Cognito User Pool exists" `
    -FailureMessage "Cognito User Pool not found"

Write-Host ""
Write-Host "7. KMS Key Rotation" -ForegroundColor Yellow
Write-Host "-----------------" -ForegroundColor Yellow

Test-SecurityControl `
    -Name "KMS Key Rotation" `
    -Test {
        $keys = aws kms list-keys --region $region 2>$null | ConvertFrom-Json
        if ($keys.Keys.Count -gt 0) {
            $keyId = $keys.Keys[0].KeyId
            $rotation = aws kms get-key-rotation-status --key-id $keyId --region $region 2>$null | ConvertFrom-Json
            return $rotation.KeyRotationEnabled -eq $true
        }
        return $false
    } `
    -SuccessMessage "KMS key rotation is enabled" `
    -FailureMessage "KMS key rotation is not enabled"

Write-Host ""
Write-Host "8. Secrets Manager" -ForegroundColor Yellow
Write-Host "----------------" -ForegroundColor Yellow

Test-SecurityControl `
    -Name "Secrets Manager Configuration" `
    -Test {
        $secrets = aws secretsmanager list-secrets --region $region 2>$null | ConvertFrom-Json
        return $secrets.SecretList.Count -gt 0
    } `
    -SuccessMessage "Secrets Manager is configured" `
    -FailureMessage "Secrets Manager not found"

Write-Host ""
Write-Host "=== Validation Summary ===" -ForegroundColor Cyan
Write-Host ""

if ($errors -eq 0) {
    Write-Host "✓ All security controls passed!" -ForegroundColor Green
    Write-Host "Your deployment is production-ready." -ForegroundColor Green
    exit 0
} else {
    Write-Host "✗ $errors security control(s) failed" -ForegroundColor Red
    Write-Host "Please review and fix the issues above before deploying to production." -ForegroundColor Yellow
    exit 1
}
