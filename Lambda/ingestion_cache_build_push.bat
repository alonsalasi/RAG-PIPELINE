@echo off
echo Building Ingestion Lambda (with cache)...

REM Login to ECR (with SSL verification disabled for corporate proxy)
for /f "tokens=*" %%i in ('aws ecr get-login-password --region us-east-1 --profile default --no-verify-ssl') do set ECR_PASSWORD=%%i
if errorlevel 1 exit /b 1
echo %ECR_PASSWORD% | docker login --username AWS --password-stdin 656008069461.dkr.ecr.us-east-1.amazonaws.com
if errorlevel 1 exit /b 1

REM Build image
docker build --platform linux/amd64 --provenance=false -t pdfquery-ingestion-lambda-production -f ingestion.Dockerfile .

REM Tag image
docker tag pdfquery-ingestion-lambda-production:latest 656008069461.dkr.ecr.us-east-1.amazonaws.com/pdfquery-ingestion-lambda-production:latest

REM Push image
docker push 656008069461.dkr.ecr.us-east-1.amazonaws.com/pdfquery-ingestion-lambda-production:latest

REM Update Lambda (with SSL verification disabled)
aws lambda update-function-code --function-name pdfquery-ingestion-worker --image-uri 656008069461.dkr.ecr.us-east-1.amazonaws.com/pdfquery-ingestion-lambda-production:latest --region us-east-1 --profile default --no-verify-ssl

echo Done!
