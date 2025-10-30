# Build and push Agent Lambda Docker image
$ErrorActionPreference = "Stop"

$PROJECT_NAME = "pdfquery"
$ENVIRONMENT = "production"
$AWS_REGION = "us-east-1"
$AWS_PROFILE = "leidos"
$AWS_ACCOUNT_ID = (aws sts get-caller-identity --profile $AWS_PROFILE --query Account --output text)

$REPO_NAME = "$PROJECT_NAME-agent-lambda-$ENVIRONMENT"
$IMAGE_TAG = "latest"

Write-Host "Building Agent Lambda Docker image..." -ForegroundColor Cyan
Set-Location Lambda
docker build --no-cache --platform linux/amd64 --provenance=false -t $REPO_NAME -f agent.Dockerfile .
if ($LASTEXITCODE -ne 0) { Write-Error "Docker build failed"; Set-Location ..; exit 1 }

Write-Host "Tagging image..." -ForegroundColor Cyan
docker tag "$REPO_NAME`:$IMAGE_TAG" "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$REPO_NAME`:$IMAGE_TAG"
if ($LASTEXITCODE -ne 0) { Write-Error "Docker tag failed"; Set-Location ..; exit 1 }

Write-Host "Logging into ECR..." -ForegroundColor Cyan
aws ecr get-login-password --region $AWS_REGION --profile $AWS_PROFILE | docker login --username AWS --password-stdin "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
if ($LASTEXITCODE -ne 0) { Write-Error "ECR login failed"; Set-Location ..; exit 1 }

Write-Host "Pushing image to ECR..." -ForegroundColor Cyan
docker push "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$REPO_NAME`:$IMAGE_TAG"
if ($LASTEXITCODE -ne 0) { Write-Error "Docker push failed"; Set-Location ..; exit 1 }

Set-Location ..
Write-Host "Agent Lambda image pushed successfully!" -ForegroundColor Green
Write-Host "Run 'terraform apply' to update the Lambda function" -ForegroundColor Yellow
