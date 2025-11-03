# Test ABBYY Cloud API Connection
param(
    [string]$Profile = "leidos",
    [string]$ProjectName = "pdfquery"
)

$secretName = "$ProjectName-abbyy-cloud-key"

Write-Host "Testing ABBYY Cloud API connection..." -ForegroundColor Cyan
Write-Host ""

# Step 1: Retrieve credentials from Secrets Manager
Write-Host "1. Retrieving credentials from Secrets Manager..." -ForegroundColor Yellow
try {
    $secretJson = aws secretsmanager get-secret-value `
        --secret-id $secretName `
        --profile $Profile `
        --query SecretString `
        --output text
    
    $credentials = $secretJson | ConvertFrom-Json
    $appId = $credentials.application_id
    $password = $credentials.password
    
    Write-Host "   ✓ Credentials retrieved" -ForegroundColor Green
    Write-Host "   Application ID: $appId" -ForegroundColor Gray
} catch {
    Write-Host "   ✗ Failed to retrieve credentials: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "Run setup first:" -ForegroundColor Yellow
    Write-Host "   .\scripts\setup-abbyy-cloud.ps1 -ApplicationId 'your_id' -Password 'your_password'" -ForegroundColor Gray
    exit 1
}

Write-Host ""

# Step 2: Test API connection
Write-Host "2. Testing ABBYY Cloud API connection..." -ForegroundColor Yellow

$base64Auth = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("${appId}:${password}"))
$headers = @{
    "Authorization" = "Basic $base64Auth"
}

try {
    $response = Invoke-WebRequest `
        -Uri "https://cloud-eu.ocrsdk.com/v2/listTasks" `
        -Method GET `
        -Headers $headers `
        -TimeoutSec 10
    
    if ($response.StatusCode -eq 200) {
        Write-Host "   ✓ Connection successful!" -ForegroundColor Green
        Write-Host ""
        
        # Parse XML to get account info
        [xml]$xml = $response.Content
        Write-Host "Account Status:" -ForegroundColor Cyan
        Write-Host "   API Endpoint: cloud-eu.ocrsdk.com" -ForegroundColor Gray
        Write-Host "   Status: Active" -ForegroundColor Green
        Write-Host ""
        Write-Host "✓ ABBYY Cloud is ready to use!" -ForegroundColor Green
        Write-Host ""
        Write-Host "Next steps:" -ForegroundColor Yellow
        Write-Host "   1. Redeploy Lambda: cd Lambda && .\ingestion_cache_build_push.bat" -ForegroundColor Gray
        Write-Host "   2. Upload a handwritten PDF to test" -ForegroundColor Gray
        Write-Host "   3. Monitor usage at https://cloud.ocrsdk.com/" -ForegroundColor Gray
    } else {
        Write-Host "   ✗ Unexpected response: $($response.StatusCode)" -ForegroundColor Red
    }
} catch {
    Write-Host "   ✗ Connection failed: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "Possible issues:" -ForegroundColor Yellow
    Write-Host "   - Invalid credentials" -ForegroundColor Gray
    Write-Host "   - ABBYY Cloud service unavailable" -ForegroundColor Gray
    Write-Host "   - Network connectivity issues" -ForegroundColor Gray
    exit 1
}
