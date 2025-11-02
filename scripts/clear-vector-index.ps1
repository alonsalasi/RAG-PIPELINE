# Clear old vector index to force rebuild with new embeddings
Write-Host "Clearing old vector index..." -ForegroundColor Yellow

$bucket = "leidos-rag-documents-production"

try {
    # Delete master index files
    aws s3 rm "s3://$bucket/vector_store/master/index.faiss"
    aws s3 rm "s3://$bucket/vector_store/master/index.pkl"
    
    Write-Host "✓ Old vector index deleted successfully" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "1. Re-upload your Hebrew PDF through the web interface" -ForegroundColor White
    Write-Host "2. Wait for processing to complete" -ForegroundColor White
    Write-Host "3. Try your English query on the Hebrew content" -ForegroundColor White
} catch {
    Write-Host "✗ Error: $_" -ForegroundColor Red
}
