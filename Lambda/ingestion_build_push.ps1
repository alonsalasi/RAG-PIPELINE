Write-Host "Building Ingestion Lambda..."

# Set environment to skip Docker auth issues
$env:DOCKER_BUILDKIT = "0"

# Login to ECR
$ecrPassword = aws ecr get-login-password --region us-east-1 --no-verify-ssl
if ($LASTEXITCODE -ne 0) { exit 1 }
$ecrPassword | docker login --username AWS --password-stdin 656008069461.dkr.ecr.us-east-1.amazonaws.com 2>&1 | Out-Null

# Build without cache to avoid auth issues
docker build --platform linux/amd64 --no-cache -t pdfquery-ingestion-lambda-production -f ingestion.Dockerfile .
if ($LASTEXITCODE -ne 0) { exit 1 }

# Tag
docker tag pdfquery-ingestion-lambda-production:latest 656008069461.dkr.ecr.us-east-1.amazonaws.com/pdfquery-ingestion-lambda-production:latest
if ($LASTEXITCODE -ne 0) { exit 1 }

# Push
docker push 656008069461.dkr.ecr.us-east-1.amazonaws.com/pdfquery-ingestion-lambda-production:latest
if ($LASTEXITCODE -ne 0) { exit 1 }

# Update Lambda
aws lambda update-function-code --function-name pdfquery-ingestion-worker --image-uri 656008069461.dkr.ecr.us-east-1.amazonaws.com/pdfquery-ingestion-lambda-production:latest --region us-east-1 --no-verify-ssl | Out-Null
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "Done!"
