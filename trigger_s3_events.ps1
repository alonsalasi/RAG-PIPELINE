$ErrorActionPreference = "SilentlyContinue"
$env:PYTHONWARNINGS = "ignore:Unverified HTTPS request"

$BUCKET = "pdfquery-rag-documents-production"

Write-Host "Fetching files from uploads/..." -ForegroundColor Cyan

# Get all files in uploads/
$files = aws s3 ls s3://$BUCKET/uploads/ --profile default --no-verify-ssl 2>$null | ForEach-Object {
    if ($_ -match '\s+(\S+)$') {
        $matches[1]
    }
}

$count = ($files | Measure-Object).Count
Write-Host "Found $count files to reprocess" -ForegroundColor Green

$processed = 0
foreach ($file in $files) {
    $s3Key = "uploads/$file"
    
    # Copy file to itself to trigger S3 event
    aws s3 cp "s3://$BUCKET/$s3Key" "s3://$BUCKET/$s3Key" --profile default --no-verify-ssl 2>$null | Out-Null
    
    $processed++
    if ($processed % 10 -eq 0) {
        Write-Host "Triggered $processed/$count files..." -ForegroundColor Yellow
    }
}

Write-Host "`n✅ Successfully triggered S3 events for $processed files!" -ForegroundColor Green
Write-Host "Lambda will process them automatically. Check progress with:" -ForegroundColor Cyan
Write-Host "aws s3 ls s3://$BUCKET/processed/ --profile default --no-verify-ssl" -ForegroundColor White
