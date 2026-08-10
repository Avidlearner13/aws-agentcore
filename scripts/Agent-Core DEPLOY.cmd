@echo off
REM Deploy / roll back the Agent-Core WEB CONSOLE on AWS App Runner by switching ECR image tag.
REM This controls the control-plane + UI image ONLY. It does NOT touch the AgentCore agents.
REM New versions are built by CodeBuild (IMAGE_TAG=vN); this script only POINTS the live
REM service at a tag that already exists in ECR. It never builds.
REM Double-click for the menu, or run:  "Agent-Core DEPLOY.cmd" v7
setlocal EnableDelayedExpansion
set "ROOT=%~dp0.."
set "PY=%ROOT%\control-plane\.venv\Scripts\python.exe"
set "SAI=%ROOT%\scripts\set-app-image.py"

if not exist "%PY%" (
  echo ERROR: Python venv not found at:
  echo   %PY%
  echo Open a terminal in the repo and create it, or run the script with your own python.
  echo.
  pause
  goto :eof
)

REM If a tag was passed on the command line, use it directly.
if not "%~1"=="" (
  set "TAG=%~1"
  goto :confirm
)

:menu
cls
echo ============================================================
echo    AGENT-CORE WEB CONSOLE  -  Deploy / Rollback
echo    (App Runner image tag switch - NOT the AgentCore agents)
echo ============================================================
echo    Currently serving:
"%PY%" "%SAI%" --show 2>nul
echo ------------------------------------------------------------
echo    Available image tags in ECR (newest first):
"%PY%" "%SAI%" --list 2>nul
echo ------------------------------------------------------------
echo    Type a tag to deploy/roll back to (e.g. v7), or leave
echo    blank and press Enter to exit.
echo ------------------------------------------------------------
set "TAG="
set /p "TAG=Tag: "
if "!TAG!"=="" goto :eof

:confirm
echo.
echo You are about to point the LIVE web console at image tag: !TAG!
choice /M "Proceed"
if errorlevel 2 goto :menu
echo.
"%PY%" "%SAI%" !TAG!
echo.
echo ------------------------------------------------------------
pause
goto :eof
