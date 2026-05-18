@echo off
setlocal

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-dev.ps1"

endlocal
