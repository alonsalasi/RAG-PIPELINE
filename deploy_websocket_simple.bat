@echo off
echo ========================================
echo WebSocket API Gateway Deployment
echo ========================================
echo.
echo Deploying WebSocket API that uses existing agent_executor Lambda...
echo.

terraform init
terraform apply -target=aws_apigatewayv2_api.websocket -target=aws_apigatewayv2_stage.websocket -target=aws_apigatewayv2_route.connect -target=aws_apigatewayv2_route.disconnect -target=aws_apigatewayv2_route.query -target=aws_apigatewayv2_integration.websocket -target=aws_lambda_permission.websocket -target=aws_iam_role_policy.agent_executor_websocket -auto-approve

if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Terraform apply failed
    exit /b 1
)

echo.
echo Getting WebSocket URL...
for /f "tokens=*" %%i in ('terraform output -raw websocket_url 2^>nul') do set WEBSOCKET_URL=%%i

echo.
echo ========================================
echo DEPLOYMENT COMPLETE!
echo ========================================
echo WebSocket URL: %WEBSOCKET_URL%
echo.
echo The existing agent_executor Lambda now handles WebSocket connections.
echo No separate Lambda needed - WebSocket support is already in the code.
echo.
echo Next: Update frontend to use WebSocket for long queries.
echo ========================================
