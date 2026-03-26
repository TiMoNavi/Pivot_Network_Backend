@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "PROJECT_ROOT=%%~fI"

if not defined TERM set "TERM=xterm-256color"
if not defined COLORTERM set "COLORTERM=truecolor"
if not defined TERM_PROGRAM set "TERM_PROGRAM=cccc"
set "CLICOLOR=1"
set "CLICOLOR_FORCE=1"
set "FORCE_COLOR=1"
set "HOME=%PROJECT_ROOT%"
set "CODEX_HOME=%PROJECT_ROOT%\.codex"

set "REAL_CODEX="
if defined CODEX_REAL_BIN if exist "%CODEX_REAL_BIN%" set "REAL_CODEX=%CODEX_REAL_BIN%"

if not defined REAL_CODEX call :consider_file "%APPDATA%\npm\codex.cmd"
if not defined REAL_CODEX call :consider_file "%APPDATA%\npm\codex"
if not defined REAL_CODEX call :consider_file "%APPDATA%\npm\codex.ps1"
if not defined REAL_CODEX for /f "delims=" %%I in ('where codex.exe 2^>nul') do call :consider_file "%%~fI"
if not defined REAL_CODEX for /f "delims=" %%I in ('where codex.cmd 2^>nul') do call :consider_file "%%~fI"
if not defined REAL_CODEX for /f "delims=" %%I in ('where codex.ps1 2^>nul') do call :consider_file "%%~fI"
if not defined REAL_CODEX for /f "delims=" %%I in ('where codex 2^>nul') do call :consider_file "%%~fI"
if not defined REAL_CODEX call :consider_vscode_extension

if not defined REAL_CODEX (
  echo Could not find the real codex binary. 1>&2
  exit /b 127
)

set "CODEX_REAL_BIN=%REAL_CODEX%"
"%REAL_CODEX%" %*
exit /b %ERRORLEVEL%

:consider_vscode_extension
for /d %%D in ("%USERPROFILE%\.vscode\extensions\openai.chatgpt-*") do (
  if exist "%%~fD\bin\windows-x86_64\codex.exe" call :consider_file "%%~fD\bin\windows-x86_64\codex.exe"
  if defined REAL_CODEX goto :eof
)
goto :eof

:consider_file
if defined REAL_CODEX goto :eof
if not exist "%~1" goto :eof
if /I "%~f1"=="%~f0" goto :eof
if /I "%~f1"=="%SCRIPT_DIR%codex.cmd" goto :eof
set "REAL_CODEX=%~f1"
goto :eof
