# Test Semantic Chunking
# This script tests the new semantic chunking functionality

Write-Host "🧪 Testing Semantic Chunking Implementation" -ForegroundColor Cyan
Write-Host "=" * 50

# Navigate to project directory
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

# Check if Python is available
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✅ Python found: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Python not found. Please install Python 3.8+" -ForegroundColor Red
    exit 1
}

# Install required packages if needed
Write-Host "`n📦 Checking dependencies..." -ForegroundColor Yellow
try {
    python -c "import langchain; print('LangChain available')" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Installing LangChain..." -ForegroundColor Yellow
        pip install langchain langchain-community
    }
} catch {
    Write-Host "Installing required packages..." -ForegroundColor Yellow
    pip install langchain langchain-community
}

# Run the test
Write-Host "`n🚀 Running semantic chunking tests..." -ForegroundColor Green
Write-Host ""

try {
    python scripts/test_semantic_chunking.py
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "`n✅ Semantic chunking tests passed!" -ForegroundColor Green
        Write-Host ""
        Write-Host "🎯 Key Improvements:" -ForegroundColor Cyan
        Write-Host "  • Tables and structured data preserved" -ForegroundColor White
        Write-Host "  • Related content blocks grouped together" -ForegroundColor White  
        Write-Host "  • Headers stay with their content" -ForegroundColor White
        Write-Host "  • Large tables split intelligently" -ForegroundColor White
        Write-Host "  • Rich metadata for better retrieval" -ForegroundColor White
        Write-Host ""
        Write-Host "📋 Next Steps:" -ForegroundColor Yellow
        Write-Host "  1. Deploy updated Lambda functions" -ForegroundColor White
        Write-Host "  2. Test with real PDF documents" -ForegroundColor White
        Write-Host "  3. Verify table preservation in search results" -ForegroundColor White
    } else {
        Write-Host "❌ Tests failed. Check the output above." -ForegroundColor Red
    }
} catch {
    Write-Host "❌ Error running tests: $_" -ForegroundColor Red
}

Write-Host "`nPress any key to continue..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")