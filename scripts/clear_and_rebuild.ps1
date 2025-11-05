# Clear vector store and rebuild with updated extraction
Write-Host "=== Clearing Vector Store and Rebuilding ===" -ForegroundColor Cyan

# 1. Delete old processed files
Write-Host "`n1. Deleting old processed files..." -ForegroundColor Yellow
aws s3 rm s3://pdfquery-rag-documents-production/processed/Hyundai.json --profile default
aws s3 rm s3://pdfquery-rag-documents-production/processed/Cherry.json --profile default

# 2. Delete vector store
Write-Host "`n2. Deleting master vector index..." -ForegroundColor Yellow
aws s3 rm s3://pdfquery-rag-documents-production/vector_store/master/index.faiss --profile default
aws s3 rm s3://pdfquery-rag-documents-production/vector_store/master/index.pkl --profile default

# 3. Delete old uploads to force reprocessing
Write-Host "`n3. Deleting old uploads..." -ForegroundColor Yellow
aws s3 rm s3://pdfquery-rag-documents-production/uploads/Hyundai.pdf --profile default
aws s3 rm s3://pdfquery-rag-documents-production/uploads/Cherry.pdf --profile default

# 4. Delete old images
Write-Host "`n4. Deleting old images..." -ForegroundColor Yellow
aws s3 rm s3://pdfquery-rag-documents-production/images/Hyundai/ --recursive --profile default
aws s3 rm s3://pdfquery-rag-documents-production/images/Cherry/ --recursive --profile default

Write-Host "`n=== Cleanup Complete ===" -ForegroundColor Green
Write-Host "`nNext steps:" -ForegroundColor Cyan
Write-Host "1. Rebuild ingestion Lambda: cd Lambda && ingestion_no_cache_build_push.bat"
Write-Host "2. Re-upload Hyundai.pdf and Cherry.pdf through the UI"
Write-Host "3. Wait for processing to complete"
Write-Host "4. Test queries"
