@echo off
set SITE=%~1
if "%SITE%"=="" set SITE=fishc

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run_now.ps1" -Site "%SITE%" -Trigger manual
echo.
echo Site=%SITE%
echo ExitCode=%ERRORLEVEL%
pause
