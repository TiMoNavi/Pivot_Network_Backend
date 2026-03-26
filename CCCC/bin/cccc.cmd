@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\run-cccc.ps1" %*
exit /b %ERRORLEVEL%
