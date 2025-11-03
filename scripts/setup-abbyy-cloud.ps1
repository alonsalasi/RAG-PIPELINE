# Setup ABBYY Cloud OCR API credentials in Secrets Manager
param(
    [Parameter(Mandatory=$true)]
    [string]$ApplicationId,
    
    [Parameter(Mandatory=$true)]
    [string]$Password,
    
    [string]$Profile = "leidos",
    [string]$ProjectName = "pdfquery"
)

$secretName = "$ProjectName-abbyy-cloud-key"

Write-Host "Storing ABBYY Cloud credentials in Secrets Manager..." -ForegroundColor Cyan

$secretValue = @{
    application_id = $ApplicationId
    password = $Password
} | ConvertTo-Json

try {
    aws secretsmanager put-secret-value `
        --secret-id $secretName `
        --secret-string $secretValue `
        --profile $Profile
    
    Write-Host "✓ ABBYY Cloud credentials stored successfully" -ForegroundColor Green
    Write-Host "Secret: $secretName" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Note: Free tier provides 500 pages/month" -ForegroundColor Yellow
} catch {
    Write-Host "✗ Failed to store credentials: $_" -ForegroundColor Red
    exit 1
}
