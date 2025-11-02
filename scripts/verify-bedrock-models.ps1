# Verify Bedrock Model Access
Write-Host "=== Bedrock Model Access Verification ===" -ForegroundColor Cyan
Write-Host ""

# Check Cohere Multilingual model
Write-Host "Checking Cohere Embed Multilingual v3..." -ForegroundColor Yellow
try {
    $modelId = "cohere.embed-multilingual-v3.0"
    $query = "modelSummaries[?modelId=='$modelId']"
    $cohereCheck = aws bedrock list-foundation-models --region us-east-1 --query $query --output json | ConvertFrom-Json
    
    if ($cohereCheck.Count -gt 0) {
        Write-Host "OK Cohere Embed Multilingual v3 is available" -ForegroundColor Green
        Write-Host "  Model ID: cohere.embed-multilingual-v3.0" -ForegroundColor Gray
    } else {
        Write-Host "ERROR Cohere Embed Multilingual v3 NOT found" -ForegroundColor Red
        Write-Host "  You need to enable this model in Bedrock Console" -ForegroundColor Yellow
    }
} catch {
    Write-Host "ERROR checking Cohere model: $_" -ForegroundColor Red
}

Write-Host ""

# Check current model access
Write-Host "Checking all embedding models..." -ForegroundColor Yellow
try {
    $allModels = aws bedrock list-foundation-models --region us-east-1 --output json | ConvertFrom-Json
    $embedModels = $allModels.modelSummaries | Where-Object { $_.modelId -like "*embed*" }
    
    foreach ($model in $embedModels) {
        Write-Host "  - $($model.modelId)" -ForegroundColor Gray
    }
} catch {
    Write-Host "ERROR listing models: $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "=== How to Enable Cohere Model ===" -ForegroundColor Cyan
Write-Host "1. Go to AWS Console - Bedrock - Model access" -ForegroundColor White
Write-Host "2. Click Manage model access" -ForegroundColor White
Write-Host "3. Find Cohere section and check Embed Multilingual v3" -ForegroundColor White
Write-Host "4. Click Request model access" -ForegroundColor White
Write-Host "5. Wait for approval (usually instant)" -ForegroundColor White
Write-Host ""
