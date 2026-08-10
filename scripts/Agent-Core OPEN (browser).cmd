@echo off
REM Double-click to open the console in your browser (must be RUNNING).
setlocal
call "%~dp0config.cmd"
if "%URL%"=="" (
  echo ERROR: App Runner service "%SVC_NAME%" not found in profile %PROFILE% ^(%REGION%^).
  pause
  goto :eof
)
start "" "%URL%"
endlocal
