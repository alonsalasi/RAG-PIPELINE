$bucket = "pdfquery-rag-documents-production"
$prefix = "uploads/"

Write-Host "Fetching files from $prefix..." -ForegroundColor Cyan
$output = aws s3 ls s3://$bucket/$prefix --recursive

if (-not $output) {
    Write-Host "No files found in $prefix" -ForegroundColor Red
    exit 1
}

$fileList = $output | ForEach-Object {
    $parts = $_ -split '\s+', 4
    if ($parts.Length -eq 4) { $parts[3] }
} | Where-Object { $_ -and $_ -notmatch '/$' }

$totalFiles = $fileList.Count
Write-Host "`nFound $totalFiles files to reprocess`n" -ForegroundColor Green

$timestamp = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$counter = 0

foreach ($key in $fileList) {
    $counter++
    
    # Add metadata to trigger S3 event
    aws s3api copy-object `
        --bucket $bucket `
        --copy-source "$bucket/$key" `
        --key $key `
        --metadata "reprocess=$timestamp" `
        --metadata-directive REPLACE | Out-Null
    
    if ($counter % 10 -eq 0) {
        Write-Host "Triggered $counter/$totalFiles files..." -ForegroundColor Yellow
    }
}

Write-Host "`nTriggered $counter/$totalFiles files...`n" -ForegroundColor Yellow
Write-Host "Successfully triggered S3 events for $totalFiles files!" -ForegroundColor Green
Write-Host "`nLambda will process them automatically. Check progress with:" -ForegroundColor Cyan
Write-Host "aws s3 ls s3://$bucket/processed/" -ForegroundColor White
