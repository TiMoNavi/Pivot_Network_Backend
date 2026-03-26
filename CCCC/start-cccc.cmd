@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0cccc-start.ps1" %*
exit /b %ERRORLEVEL%
