@echo off
echo ========================================
echo WebSocket API Gateway Deployment
echo ========================================
echo.

REM Step 1: Build and push WebSocket handler Docker image
echo Step 1: Building and pushing WebSocket handler Docker image...
cd Lambda
call websocket_build_push.bat
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Docker build/push failed
    exit /b 1
)
cd ..

REM Step 2: Deploy WebSocket infrastructure with Terraform
echo.
echo Step 2: Deploying WebSocket infrastructure with Terraform...
terraform init
terraform plan -target=aws_apigatewayv2_api.websocket -target=aws_apigatewayv2_stage.websocket -target=aws_lambda_function.websocket_handler -target=aws_ecr_repository.websocket_handler -target=aws_iam_role.websocket_lambda_role -target=aws_iam_role_policy.websocket_lambda_policy -target=aws_apigatewayv2_route.connect -target=aws_apigatewayv2_route.disconnect -target=aws_apigatewayv2_route.query -target=aws_apigatewayv2_integration.connect -target=aws_apigatewayv2_integration.disconnect -target=aws_apigatewayv2_integration.query -target=aws_lambda_permission.websocket_connect

echo.
echo Applying Terraform changes...

terraform apply -target=aws_apigatewayv2_api.websocket -target=aws_apigatewayv2_stage.websocket -target=aws_lambda_function.websocket_handler -target=aws_ecr_repository.websocket_handler -target=aws_iam_role.websocket_lambda_role -target=aws_iam_role_policy.websocket_lambda_policy -target=aws_apigatewayv2_route.connect -target=aws_apigatewayv2_route.disconnect -target=aws_apigatewayv2_route.query -target=aws_apigatewayv2_integration.connect -target=aws_apigatewayv2_integration.disconnect -target=aws_apigatewayv2_integration.query -target=aws_lambda_permission.websocket_connect -auto-approve

if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Terraform apply failed
    exit /b 1
)

REM Step 3: Get WebSocket URL
echo.
echo Step 3: Getting WebSocket URL...
for /f "tokens=*" %%i in ('terraform output -raw websocket_url 2^>nul') do set WEBSOCKET_URL=%%i

if "%WEBSOCKET_URL%"=="" (
    echo ERROR: Could not get WebSocket URL from Terraform output
    exit /b 1
)

echo.
echo ========================================
echo Deployment Complete!
echo ========================================
echo WebSocket URL: %WEBSOCKET_URL%
echo.
echo Next steps:
echo 1. Update frontend index.html with WebSocket URL
echo 2. Deploy updated frontend to S3
echo 3. Invalidate CloudFront cache
echo ========================================
