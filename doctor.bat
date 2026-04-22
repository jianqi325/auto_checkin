@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\doctor.ps1" -Site fishc
pause
