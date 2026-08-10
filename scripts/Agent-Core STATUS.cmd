@echo off
REM Double-click to check whether the console is RUNNING / PAUSED.
echo Current status:
call "%~dp0apprunner.cmd" status
echo.
pause
