# Setup Google Vision API Key in Secrets Manager
param(
    [Parameter(Mandatory=$true)]
    [string]$ApiKey,
    
    [string]$Profile = "leidos",
    [string]$ProjectName = "pdfquery"
)

$secretName = "$ProjectName-google-vision-key"

Write-Host "Storing Google Vision API key in Secrets Manager..." -ForegroundColor Cyan

$secretValue = @{
    api_key = $ApiKey
} | ConvertTo-Json

try {
    aws secretsmanager put-secret-value `
        --secret-id $secretName `
        --secret-string $secretValue `
        --profile $Profile
    
    Write-Host "✓ Google Vision API key stored successfully" -ForegroundColor Green
    Write-Host "Secret: $secretName" -ForegroundColor Gray
} catch {
    Write-Host "✗ Failed to store API key: $_" -ForegroundColor Red
    exit 1
}
