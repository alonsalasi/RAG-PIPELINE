# Rebuild master index by deleting and re-uploading a file
# This forces the index to be rebuilt with new chunk settings

Write-Host "Rebuilding master index with new chunk size..." -ForegroundColor Cyan

# Get a processed file to re-trigger
$files = aws s3 ls s3://pdfquery-rag-documents-production/processed/ --profile default | Select-String "\.json"

if ($files) {
    $firstFile = ($files | Select-Object -First 1) -replace '.*\s+', ''
    $fileName = $firstFile -replace '\.json$', ''
    
    Write-Host "Re-triggering processing for: $fileName" -ForegroundColor Yellow
    
    # Download the PDF
    aws s3 cp "s3://pdfquery-rag-documents-production/uploads/$fileName.pdf" "$fileName.pdf" --profile default
    
    # Delete the file (this will trigger rebuild)
    Write-Host "Deleting file to trigger rebuild..." -ForegroundColor Yellow
    aws s3 rm "s3://pdfquery-rag-documents-production/processed/$fileName.json" --profile default
    aws s3 rm "s3://pdfquery-rag-documents-production/vector_store/master/index.faiss" --profile default
    aws s3 rm "s3://pdfquery-rag-documents-production/vector_store/master/index.pkl" --profile default
    
    # Re-upload the PDF
    Write-Host "Re-uploading PDF to trigger reprocessing..." -ForegroundColor Yellow
    aws s3 cp "$fileName.pdf" "s3://pdfquery-rag-documents-production/uploads/$fileName.pdf" --profile default
    
    # Clean up local file
    Remove-Item "$fileName.pdf" -ErrorAction SilentlyContinue
    
    Write-Host "Done! Wait for processing to complete, then master index will be rebuilt with new chunk size." -ForegroundColor Green
} else {
    Write-Host "No processed files found!" -ForegroundColor Red
}
