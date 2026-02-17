# Quick Deploy - PDF Ingestion Fix
# Run this script to rebuild and deploy the ingestion Lambda with the PDF OCR fix

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "PDF Ingestion Fix - Deployment" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "This will rebuild the ingestion Lambda with OCR fallback for image-based PDFs" -ForegroundColor Yellow
Write-Host ""

$confirm = Read-Host "Continue? (y/n)"
if ($confirm -ne 'y') {
    Write-Host "Deployment cancelled" -ForegroundColor Red
    exit
}

Write-Host ""
Write-Host "Building and pushing ingestion Lambda..." -ForegroundColor Green

# Change to Lambda directory
Set-Location -Path "c:\Projects\Leidos\RAG-PIpeline\RAG-PIPELINE-1\Lambda"

# Run the build script
& .\ingestion_no_cache_build_push.bat

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Deployment Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "The ingestion Lambda now supports:" -ForegroundColor Yellow
Write-Host "  ✓ Fast text extraction for text-based PDFs" -ForegroundColor Green
Write-Host "  ✓ OCR fallback for scanned/image-based PDFs" -ForegroundColor Green
Write-Host "  ✓ Multilingual support (English, Hebrew, Arabic)" -ForegroundColor Green
Write-Host ""
Write-Host "Test by uploading a scanned PDF document" -ForegroundColor Cyan
