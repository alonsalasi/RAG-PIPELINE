#!/usr/bin/env pwsh
<#
.SYNOPSIS
Rebuilds the vector index by deleting the old one and triggering a rebuild
#>

param(
    [string]$Profile = "default",
    [string]$Region = "us-east-1",
    [string]$Bucket = "pdfquery-rag-documents-production"
)

Write-Host "🗑️  Deleting old vector index..." -ForegroundColor Yellow

# Delete old index files
aws s3 rm "s3://$Bucket/vector_store/master/index.faiss" --profile $Profile --region $Region
aws s3 rm "s3://$Bucket/vector_store/master/index.pkl" --profile $Profile --region $Region

Write-Host "✅ Old index deleted" -ForegroundColor Green
Write-Host ""
Write-Host "⚠️  NEXT STEPS:" -ForegroundColor Cyan
Write-Host "  1. Re-upload your documents, OR"
Write-Host "  2. Manually invoke the Lambda rebuild function"
Write-Host ""
Write-Host "The index will be automatically rebuilt when:"
Write-Host "  - New documents are uploaded and processed"
Write-Host "  - Documents are deleted (triggers auto-rebuild)"
Write-Host ""
