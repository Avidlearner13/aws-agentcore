@echo off
REM Agent-Core console control (AWS App Runner) - interactive menu.
REM Double-click to run. Shows live status and lets you start/stop/open.
REM Account/profile/service settings live in config.cmd.
setlocal EnableDelayedExpansion
call "%~dp0config.cmd"
REM Put the AWS CLI on PATH so we can call `aws` unquoted (needed for the status capture below).
set "PATH=C:\Program Files\Amazon\AWSCLIV2;%PATH%"

if "%SVC%"=="" (
  echo ERROR: App Runner service "%SVC_NAME%" not found in profile %PROFILE% ^(%REGION%^).
  echo Has it been created yet?
  pause
  goto end
)

:menu
cls
echo ============================================================
echo    AGENT-CORE CONSOLE  -  AWS App Runner control
echo ============================================================
echo    URL : %URL%
echo    User: anuproy2026
echo.
echo    Checking status...
set "STATUS=unknown"
for /f "usebackq delims=" %%S in (`aws apprunner describe-service --service-arn "%SVC%" --region %REGION% --profile %PROFILE% --query "Service.Status" --output text 2^>nul`) do set "STATUS=%%S"
echo    CURRENT STATUS : !STATUS!
echo ------------------------------------------------------------
echo    [1] Start  (resume - ~3-5 min to RUNNING)
echo    [2] Stop   (pause  - stops billing)
echo    [3] Refresh status
echo    [4] Open in browser
echo    [5] Exit
echo ------------------------------------------------------------
set "CHOICE="
set /p "CHOICE=Choose 1-5: "

if "!CHOICE!"=="1" goto do_resume
if "!CHOICE!"=="2" goto do_pause
if "!CHOICE!"=="3" goto menu
if "!CHOICE!"=="4" goto do_open
if "!CHOICE!"=="5" goto end
goto menu

:do_resume
echo.
echo Resuming the console...
aws apprunner resume-service --service-arn "%SVC%" --region %REGION% --profile %PROFILE% --query "Service.Status" --output text
echo.
echo Started. It takes ~3-5 minutes to reach RUNNING - use [3] Refresh to watch.
pause
goto menu

:do_pause
echo.
echo Pausing the console (stops billing)...
aws apprunner pause-service --service-arn "%SVC%" --region %REGION% --profile %PROFILE% --query "Service.Status" --output text
echo.
pause
goto menu

:do_open
if /I not "!STATUS!"=="RUNNING" echo NOTE: status is !STATUS! - open works best when RUNNING.
start "" "%URL%"
goto menu

:end
endlocal
