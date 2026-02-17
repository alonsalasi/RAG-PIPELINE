# Rebuild master index by re-triggering processing for all uploaded files
$bucket = "pdfquery-rag-documents-production"

Write-Host "Fetching all uploaded files..." -ForegroundColor Cyan
$files = aws s3 ls s3://$bucket/uploads/ --recursive --profile default --no-verify-ssl | ForEach-Object {
    $parts = $_ -split '\s+', 4
    if ($parts.Count -eq 4) {
        $parts[3]
    }
}

$fileCount = ($files | Measure-Object).Count
Write-Host "Found $fileCount files to reprocess" -ForegroundColor Yellow

if ($fileCount -eq 0) {
    Write-Host "No files found in uploads/" -ForegroundColor Red
    exit 1
}

Write-Host "`nClearing master index..." -ForegroundColor Cyan
aws s3 rm s3://$bucket/vector_store/master/index.faiss --profile default --no-verify-ssl 2>$null
aws s3 rm s3://$bucket/vector_store/master/index.pkl --profile default --no-verify-ssl 2>$null

Write-Host "Clearing processed markers..." -ForegroundColor Cyan
aws s3 rm s3://$bucket/processed/ --recursive --profile default --no-verify-ssl 2>$null

Write-Host "`nTriggering reprocessing for all files..." -ForegroundColor Cyan
$count = 0
foreach ($file in $files) {
    $count++
    $fileName = Split-Path $file -Leaf
    Write-Host "[$count/$fileCount] Triggering: $fileName" -ForegroundColor Gray
    
    # Copy file to itself to trigger S3 event
    aws s3 cp s3://$bucket/$file s3://$bucket/$file --profile default --no-verify-ssl --metadata-directive REPLACE 2>$null
    
    # Small delay to avoid overwhelming Lambda
    Start-Sleep -Milliseconds 500
}

Write-Host "`nReprocessing triggered for all $fileCount files!" -ForegroundColor Green
Write-Host "Monitor progress in the UI. This will take a few minutes." -ForegroundColor Yellow
