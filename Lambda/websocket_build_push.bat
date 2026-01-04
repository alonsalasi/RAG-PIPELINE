@echo off
echo Building and pushing WebSocket handler Docker image...

REM Get AWS account ID
for /f "tokens=*" %%i in ('aws sts get-caller-identity --query Account --output text') do set AWS_ACCOUNT_ID=%%i
set AWS_REGION=us-east-1
set ECR_REPO=%AWS_ACCOUNT_ID%.dkr.ecr.%AWS_REGION%.amazonaws.com/pdfquery-websocket-handler-production

echo AWS Account: %AWS_ACCOUNT_ID%
echo ECR Repository: %ECR_REPO%

REM Login to ECR
echo Logging in to ECR...
aws ecr get-login-password --region %AWS_REGION% | docker login --username AWS --password-stdin %ECR_REPO%

REM Build Docker image
echo Building Docker image...
docker build -f websocket.Dockerfile -t pdfquery-websocket-handler:latest .

REM Tag image
echo Tagging image...
docker tag pdfquery-websocket-handler:latest %ECR_REPO%:latest

REM Push to ECR
echo Pushing to ECR...
docker push %ECR_REPO%:latest

echo Done! WebSocket handler image pushed successfully.
