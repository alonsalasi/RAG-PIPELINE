@echo off
echo ========================================
echo COMPLETE WEBSOCKET DEPLOYMENT
echo ========================================
echo.

REM Step 1: Create ECR repository first
echo STEP 1: Creating ECR Repository
terraform init
terraform apply -target=aws_ecr_repository.websocket_handler -auto-approve
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: ECR repository creation failed
    exit /b 1
)

REM Step 2: Build and push WebSocket handler
echo.
echo STEP 2: Building and Pushing WebSocket Handler
cd Lambda
call websocket_build_push.bat
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Docker build/push failed
    exit /b 1
)
cd ..

REM Step 3: Deploy WebSocket infrastructure
echo.
echo STEP 3: Deploying WebSocket Infrastructure
terraform apply -target=aws_apigatewayv2_api.websocket -target=aws_apigatewayv2_stage.websocket -target=aws_lambda_function.websocket_handler -target=aws_iam_role.websocket_lambda_role -target=aws_iam_role_policy.websocket_lambda_policy -target=aws_apigatewayv2_route.connect -target=aws_apigatewayv2_route.disconnect -target=aws_apigatewayv2_route.query -target=aws_apigatewayv2_integration.connect -target=aws_apigatewayv2_integration.disconnect -target=aws_apigatewayv2_integration.query -target=aws_lambda_permission.websocket_connect -auto-approve
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: WebSocket infrastructure deployment failed
    exit /b 1
)

REM Step 4: Update agent_executor Lambda
echo.
echo STEP 4: Updating Agent Executor Lambda
cd Lambda
call agent_cache_build_ecr_push.bat
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Agent executor update failed
    exit /b 1
)
cd ..

echo Waiting 10 seconds for Lambda to update...
timeout /t 10 /nobreak

REM Step 5: Update frontend
echo.
echo STEP 5: Updating Frontend
call update_frontend_websocket.bat
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Frontend update failed
    exit /b 1
)

echo.
echo ========================================
echo DEPLOYMENT COMPLETE!
echo ========================================
