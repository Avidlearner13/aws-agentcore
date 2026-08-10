@echo off
REM ============================================================
REM  Agent-Core - per-account settings. Edit THIS FILE ONLY when
REM  moving to a different AWS account. Every other script calls
REM  it, so nothing else hardcodes an account, ARN, or URL.
REM
REM  Deliberately contains no account ID and no service ARN: the
REM  App Runner ARN and public URL are looked up by service name
REM  at runtime, so this file is safe to commit.
REM ============================================================

set "AWS=C:\Program Files\Amazon\AWSCLIV2\aws.exe"
set "PROFILE=agentcore-personal"
set "REGION=us-east-1"
set "SVC_NAME=agent-core-console"
set "ECR_REPO=agent-core-control-plane"

REM --- resolve the App Runner service ARN by name (blank until created) ---
set "SVC="
for /f "usebackq delims=" %%A in (`"%AWS%" apprunner list-services --region %REGION% --profile %PROFILE% --query "ServiceSummaryList[?ServiceName=='%SVC_NAME%'].ServiceArn | [0]" --output text 2^>nul`) do set "SVC=%%A"
if "%SVC%"=="None" set "SVC="

REM --- resolve the public URL from the service itself ---
set "URL="
if not "%SVC%"=="" (
  for /f "usebackq delims=" %%U in (`"%AWS%" apprunner describe-service --service-arn "%SVC%" --region %REGION% --profile %PROFILE% --query "Service.ServiceUrl" --output text 2^>nul`) do set "URL=https://%%U"
)
