@echo off
echo Building Agent Lambda (no cache)...

REM Login to ECR
for /f "tokens=*" %%i in ('aws ecr get-login-password --region us-east-1') do set ECR_PASSWORD=%%i
echo %ECR_PASSWORD% | docker login --username AWS --password-stdin 656008069461.dkr.ecr.us-east-1.amazonaws.com

REM Build image with memory limits
docker build --no-cache --platform linux/amd64 --provenance=false --memory=4g --memory-swap=4g -t pdfquery-agent-lambda-production -f agent.Dockerfile .
if %ERRORLEVEL% neq 0 (
    echo Docker build failed with error %ERRORLEVEL%
    exit /b %ERRORLEVEL%
)

REM Tag image
docker tag pdfquery-agent-lambda-production:latest 656008069461.dkr.ecr.us-east-1.amazonaws.com/pdfquery-agent-lambda-production:latest

REM Push image
docker push 656008069461.dkr.ecr.us-east-1.amazonaws.com/pdfquery-agent-lambda-production:latest

REM Update Lambda
aws lambda update-function-code --function-name pdfquery-agent-executor --image-uri 656008069461.dkr.ecr.us-east-1.amazonaws.com/pdfquery-agent-lambda-production:latest --region us-east-1

echo Done!
