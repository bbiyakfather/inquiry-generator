@echo off
rem ============================================================
rem  Naevion Quote Generator launcher
rem  NOTE: keep this file ASCII-only. Korean text inside a .bat
rem  saved as UTF-8 breaks cmd.exe line parsing on ko-KR Windows
rem  (CP949), so the batch silently dies before reaching Python.
rem ============================================================
title Naevion Quote Generator
cd /d "%~dp0"

rem -- Pick the Python that has the dependencies installed.
rem    Bare "python" can resolve to the 0-byte Microsoft Store
rem    stub when launched from Explorer, which exits silently.
set "PYRUN="
py -3.12 -c "import sys" >nul 2>nul
if not errorlevel 1 set "PYRUN=py -3.12"
if not defined PYRUN if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYRUN=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PYRUN if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set "PYRUN=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not defined PYRUN set "PYRUN=python"

rem -- Core dependency check --
%PYRUN% -c "import webview, openpyxl, requests" >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Required libraries are missing. Install with:
  echo     %PYRUN% -m pip install -r requirements.txt
  echo.
  pause
  exit /b 1
)

rem -- Warn if Hancom HWP is running (COM automation conflict) --
tasklist /FI "IMAGENAME eq Hwp.exe" 2>nul | find /I "Hwp.exe" >nul
if not errorlevel 1 (
  echo [NOTICE] Hancom HWP is running. Close it before generating quotes.
  echo.
)

%PYRUN% app.py %*
if errorlevel 1 (
  echo.
  echo [ERROR] The program exited abnormally. Check app-log.txt.
  pause
)
