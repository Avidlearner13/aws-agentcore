@echo off
REM Run the governance console ON YOUR LAPTOP. Opens http://127.0.0.1:8770
REM The live AWS site is NOT touched. This local server talks to your real (deployed)
REM AgentCore agents, so the Governance demo works end-to-end.
REM Close this window (or press Ctrl+C) to stop the local server.
REM Account/profile settings live in config.cmd; runtime ARNs are resolved by name.
setlocal
call "%~dp0config.cmd"
set "ROOT=%~dp0.."
set "PY=%ROOT%\control-plane\.venv\Scripts\python.exe"

if not exist "%PY%" (
  echo ERROR: Python venv not found at  %PY%
  echo.
  echo Create it first:
  echo    cd %ROOT%\control-plane
  echo    python -m venv .venv
  echo    .venv\Scripts\pip install -r requirements.txt
  echo.
  pause
  goto :eof
)

set "AWS_PROFILE=%PROFILE%"
set "AWS_REGION=%REGION%"
set "PORT=8770"

echo Resolving AgentCore runtime ARNs...
for %%N in (intake coverage risk orchestrator) do (
  for /f "usebackq delims=" %%A in (`aws bedrock-agentcore-control list-agent-runtimes --region %REGION% --profile %PROFILE% --query "agentRuntimes[?agentRuntimeName=='%%N'].agentRuntimeArn | [0]" --output text 2^>nul`) do (
    if /I "%%N"=="intake"       set "INTAKE_ARN=%%A"
    if /I "%%N"=="coverage"     set "COVERAGE_ARN=%%A"
    if /I "%%N"=="risk"         set "RISK_ARN=%%A"
    if /I "%%N"=="orchestrator" set "ORCH_CLAUDE_ARN=%%A"
  )
)

echo ============================================================
echo    AGENT-CORE CONSOLE  -  LOCAL  (governance)
echo ============================================================
echo    URL : http://127.0.0.1:8770    (opening in your browser)
echo    Tab : click  "Governance - Cert Gate"
echo    Live AWS site is untouched. Close this window to stop.
echo ------------------------------------------------------------
start "" http://127.0.0.1:8770/
cd /d "%ROOT%\control-plane\app"
"%PY%" main.py
echo.
echo (server stopped)
pause
endlocal
