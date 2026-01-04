@echo off
setlocal enabledelayedexpansion

echo ========================================
echo Frontend WebSocket Update
echo ========================================
echo.

REM Get WebSocket URL from Terraform
echo Getting WebSocket URL from Terraform...
for /f "tokens=*" %%i in ('terraform output -raw websocket_url 2^>nul') do set WEBSOCKET_URL=%%i

if "%WEBSOCKET_URL%"=="" (
    echo ERROR: Could not get WebSocket URL from Terraform output
    echo Make sure you've deployed the WebSocket infrastructure first
    exit /b 1
)

echo WebSocket URL: %WEBSOCKET_URL%
echo.

REM Create backup
echo Creating backup of index.html...
copy index.html index.html.backup

REM Add WebSocket URL constant to index.html
echo Adding WebSocket URL to index.html...
powershell -Command "(Get-Content index.html) -replace 'const API_GATEWAY_URL = ''https://rm8vvz79d0.execute-api.us-east-1.amazonaws.com/production'';', 'const API_GATEWAY_URL = ''https://rm8vvz79d0.execute-api.us-east-1.amazonaws.com/production'';`r`n  const WEBSOCKET_URL = ''%WEBSOCKET_URL%'';' | Set-Content index.html"

REM Upload to S3
echo.
echo Uploading to S3...
aws s3 cp index.html s3://pdfquery-frontend-production/index.html --content-type "text/html; charset=utf-8"

if %ERRORLEVEL% NEQ 0 (
    echo ERROR: S3 upload failed
    echo Restoring backup...
    copy index.html.backup index.html
    del index.html.backup
    exit /b 1
)

REM Invalidate CloudFront
echo.
echo Invalidating CloudFront cache...
aws cloudfront create-invalidation --distribution-id E3FV318ZM2XSWY --paths "/*"

echo.
echo ========================================
echo Frontend Updated Successfully!
echo ========================================
echo WebSocket URL: %WEBSOCKET_URL%
echo.
echo The frontend now has WebSocket support for long-running queries.
echo CloudFront cache invalidation in progress (takes 1-2 minutes).
echo ========================================
