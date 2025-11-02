# Verify Lambda IAM Permissions for Bedrock
Write-Host "=== Lambda IAM Role Verification ===" -ForegroundColor Cyan
Write-Host ""

$roleName = "leidos-rag-lambda-agent-role-production"

Write-Host "Checking role: $roleName" -ForegroundColor Yellow
Write-Host ""

# Get role policies
Write-Host "Attached Policies:" -ForegroundColor Yellow
try {
    $attachedPolicies = aws iam list-attached-role-policies --role-name $roleName --output json | ConvertFrom-Json
    foreach ($policy in $attachedPolicies.AttachedPolicies) {
        Write-Host "  ✓ $($policy.PolicyName)" -ForegroundColor Green
    }
} catch {
    Write-Host "  ✗ Error: $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "Inline Policies:" -ForegroundColor Yellow
try {
    $inlinePolicies = aws iam list-role-policies --role-name $roleName --output json | ConvertFrom-Json
    foreach ($policyName in $inlinePolicies.PolicyNames) {
        Write-Host "  ✓ $policyName" -ForegroundColor Green
    }
} catch {
    Write-Host "  ✗ Error: $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "Checking Bedrock permissions in policy..." -ForegroundColor Yellow
try {
    $policyDoc = aws iam get-role-policy --role-name $roleName --policy-name "leidos-rag-lambda-agent-policy-production" --output json | ConvertFrom-Json
    $policyJson = $policyDoc.PolicyDocument | ConvertTo-Json -Depth 10
    
    if ($policyJson -match "bedrock:InvokeModel") {
        Write-Host "  ✓ bedrock:InvokeModel permission found" -ForegroundColor Green
    } else {
        Write-Host "  ✗ bedrock:InvokeModel permission NOT found" -ForegroundColor Red
    }
    
    if ($policyJson -match "bedrock:InvokeModelWithResponseStream") {
        Write-Host "  ✓ bedrock:InvokeModelWithResponseStream permission found" -ForegroundColor Green
    } else {
        Write-Host "  ✗ bedrock:InvokeModelWithResponseStream permission NOT found" -ForegroundColor Red
    }
} catch {
    Write-Host "  ✗ Error checking policy: $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "=== Summary ===" -ForegroundColor Cyan
Write-Host "If permissions are missing, run: terraform apply" -ForegroundColor Yellow
Write-Host ""
