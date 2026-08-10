@echo off
REM Turn the Agent-Core console (App Runner) on/off to control cost.
REM Usage:  apprunner.cmd pause | resume | status | url
REM Paused = $0 compute; Resume takes ~3-5 min to return to RUNNING.
REM Account/profile/service settings live in config.cmd.
setlocal
call "%~dp0config.cmd"

if "%~1"=="" goto usage

if "%SVC%"=="" (
  echo ERROR: App Runner service "%SVC_NAME%" not found in profile %PROFILE% ^(%REGION%^).
  echo Has it been created yet?
  goto end
)

if /I "%~1"=="pause" (
  echo Pausing Agent-Core console...
  "%AWS%" apprunner pause-service  --service-arn "%SVC%" --region %REGION% --profile %PROFILE% --query "Service.Status" --output text
  goto end
)
if /I "%~1"=="resume" (
  echo Resuming Agent-Core console... ^(give it ~3-5 min, then check 'status'^)
  "%AWS%" apprunner resume-service --service-arn "%SVC%" --region %REGION% --profile %PROFILE% --query "Service.Status" --output text
  echo URL: %URL%
  goto end
)
if /I "%~1"=="status" (
  "%AWS%" apprunner describe-service --service-arn "%SVC%" --region %REGION% --profile %PROFILE% --query "Service.Status" --output text
  goto end
)
if /I "%~1"=="url" (
  echo %URL%
  goto end
)

:usage
echo Usage: apprunner.cmd [pause ^| resume ^| status ^| url]
echo   pause   - stop the console ^(stops billing^)
echo   resume  - start it again ^(~3-5 min to RUNNING^)
echo   status  - show current status
echo   url     - print the public URL

:end
endlocal
