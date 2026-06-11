@echo off
rem  Debug launcher - keep ASCII-only (see note in the main .bat).
title Naevion Quote Generator (debug)
cd /d "%~dp0"

echo ============================================
echo  Debug mode - app output goes to run-log.txt
echo ============================================
echo.

set "PYRUN="
py -3.12 -c "import sys" >nul 2>nul
if not errorlevel 1 set "PYRUN=py -3.12"
if not defined PYRUN if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYRUN=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PYRUN set "PYRUN=python"

echo [1] Python: %PYRUN%
%PYRUN% --version
echo.

echo [2] Dependency check:
%PYRUN% -c "import webview, openpyxl, requests; print('    core OK')"
if errorlevel 1 (
  echo     [ERROR] Missing dependencies. Run:
  echo         %PYRUN% -m pip install -r requirements.txt
  echo.
  pause
  exit /b 1
)
echo.

echo [3] Starting app - the window should appear now...
%PYRUN% app.py --debug > run-log.txt 2>&1
set RC=%errorlevel%
echo.
echo ============================================
echo  Exit code: %RC%   (0 = normal)
echo  Logs: run-log.txt / app-log.txt
echo ============================================
pause
