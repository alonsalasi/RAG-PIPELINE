@echo off
echo ========================================
echo Updating Bedrock Agent Configuration
echo ========================================
echo.

echo Step 1: Applying Terraform changes...
terraform apply -target=aws_bedrockagent_agent.rag_agent -auto-approve
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Terraform apply failed
    exit /b 1
)
echo.

echo Step 2: Preparing agent (creating new version)...
for /f "tokens=*" %%i in ('terraform output -raw bedrock_agent_id 2^>nul') do set AGENT_ID=%%i
if "%AGENT_ID%"=="" (
    echo ERROR: Could not get agent ID from terraform
    exit /b 1
)

aws bedrock-agent prepare-agent --agent-id %AGENT_ID% --region us-east-1 --profile default
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Agent preparation failed
    exit /b 1
)
echo.

echo Step 3: Waiting for agent to be ready...
timeout /t 30 /nobreak
echo.

echo ========================================
echo SUCCESS! Agent updated with new instructions
echo ========================================
echo.
echo Next steps:
echo 1. Test the agent with a question about your PDFs
echo 2. Check CloudWatch logs for "SEARCH ACTION CALLED"
echo 3. If search is still not called, you may need to:
echo    - Create a new agent version in AWS Console
echo    - Update the alias to point to the new version
echo.
pause
