# Force reprocess a document by deleting its processed marker
param(
    [Parameter(Mandatory=$true)]
    [string]$FileName
)

$bucket = "pdfquery-rag-documents-production"

Write-Host "Forcing reprocess of: $FileName" -ForegroundColor Yellow

# Remove .json extension if present
$baseName = $FileName -replace '\.json$', ''

# Delete processed marker to trigger reprocessing
Write-Host "Deleting processed marker..." -ForegroundColor Cyan
aws s3 rm "s3://$bucket/processed/$baseName.json" --profile default

# Delete progress marker
Write-Host "Deleting progress marker..." -ForegroundColor Cyan
aws s3 rm "s3://$bucket/progress/$baseName.json" --profile default 2>$null

# Trigger reprocessing by touching the upload file
Write-Host "Triggering reprocessing..." -ForegroundColor Cyan
$uploadKey = "uploads/$baseName"

# Find the actual upload file (could be .pdf, .docx, etc.)
$files = aws s3 ls "s3://$bucket/$uploadKey" --profile default --recursive | Select-String $baseName

if ($files) {
    $actualFile = ($files | Select-Object -First 1) -replace '.*\s+', ''
    Write-Host "Found file: $actualFile" -ForegroundColor Green
    
    # Copy file to itself to trigger S3 event
    aws s3 cp "s3://$bucket/$actualFile" "s3://$bucket/$actualFile" --profile default --metadata-directive REPLACE
    
    Write-Host "`nReprocessing triggered! Check progress with:" -ForegroundColor Green
    Write-Host "  aws s3 cp s3://$bucket/progress/$baseName.json - --profile default" -ForegroundColor White
} else {
    Write-Host "ERROR: Upload file not found for $baseName" -ForegroundColor Red
}
