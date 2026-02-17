$ErrorActionPreference = "SilentlyContinue"
$env:PYTHONWARNINGS = "ignore:Unverified HTTPS request"

$BUCKET = "pdfquery-rag-documents-production"
$QUEUE_URL = "https://sqs.us-east-1.amazonaws.com/656008069461/pdfquery-ingestion-queue"

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
    
    # Create S3 event message
    $message = @{
        Records = @(
            @{
                eventVersion = "2.1"
                eventSource = "aws:s3"
                eventName = "ObjectCreated:Put"
                s3 = @{
                    bucket = @{ name = $BUCKET }
                    object = @{ key = $s3Key }
                }
            }
        )
    } | ConvertTo-Json -Compress -Depth 10
    
    # Send to SQS
    aws sqs send-message --queue-url $QUEUE_URL --message-body $message --profile default --no-verify-ssl 2>$null | Out-Null
    
    $processed++
    if ($processed % 10 -eq 0) {
        Write-Host "Queued $processed/$count files..." -ForegroundColor Yellow
    }
}

Write-Host "`n✅ Successfully queued $processed files for reprocessing!" -ForegroundColor Green
Write-Host "Processing will take 10-15 minutes. Check progress with:" -ForegroundColor Cyan
Write-Host "aws s3 ls s3://$BUCKET/processed/ --profile default --no-verify-ssl" -ForegroundColor White
