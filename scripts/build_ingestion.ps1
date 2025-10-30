# Build and push ingestion Lambda Docker image to ECR

$ErrorActionPreference = "Stop"

$AWS_PROFILE = "leidos"
$AWS_REGION = "us-east-1"
$ACCOUNT_ID = (aws sts get-caller-identity --profile $AWS_PROFILE --query Account --output text)
$PROJECT_NAME = "pdfquery"
$ENVIRONMENT = "production"
$REPO_NAME = "$PROJECT_NAME-ingestion-lambda-$ENVIRONMENT"
$ECR_URI = "$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$REPO_NAME"

Write-Host "Building and pushing ingestion Lambda image..." -ForegroundColor Green

# Login to ECR
Write-Host "Logging into ECR..." -ForegroundColor Yellow
aws ecr get-login-password --region $AWS_REGION --profile $AWS_PROFILE | docker login --username AWS --password-stdin "$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"

# Build image
Write-Host "Building Docker image..." -ForegroundColor Yellow
docker build --platform linux/amd64 --provenance=false -t ${ECR_URI}:latest -f Lambda/ingestion.Dockerfile ./Lambda
if ($LASTEXITCODE -ne 0) { Write-Error "Docker build failed"; exit 1 }

# Push image
Write-Host "Pushing to ECR..." -ForegroundColor Yellow
docker push ${ECR_URI}:latest
if ($LASTEXITCODE -ne 0) { Write-Error "Docker push failed"; exit 1 }

Write-Host "Done! Image pushed to $ECR_URI:latest" -ForegroundColor Green
