@echo off
echo Building Agent Lambda (with cache)...

REM Login to ECR
for /f "tokens=*" %%i in ('aws ecr get-login-password --region us-east-1 --profile leidos') do set ECR_PASSWORD=%%i
echo %ECR_PASSWORD% | docker login --username AWS --password-stdin 656008069461.dkr.ecr.us-east-1.amazonaws.com

REM Build image
docker build --platform linux/amd64 --provenance=false -t pdfquery-agent-lambda-production -f agent.Dockerfile .

REM Tag image
docker tag pdfquery-agent-lambda-production:latest 656008069461.dkr.ecr.us-east-1.amazonaws.com/pdfquery-agent-lambda-production:latest

REM Push image
docker push 656008069461.dkr.ecr.us-east-1.amazonaws.com/pdfquery-agent-lambda-production:latest

REM Update Lambda
aws lambda update-function-code --function-name pdfquery-agent-executor --image-uri 656008069461.dkr.ecr.us-east-1.amazonaws.com/pdfquery-agent-lambda-production:latest --region us-east-1 --profile leidos

echo Done!
