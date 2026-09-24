@echo off
REM WorkBuddy2API one-click installer launcher (ASCII only - do not add Chinese here)
REM GBK console would mangle UTF-8 Chinese in .bat files, so all text lives in install.py
chcp 65001 >nul
cd /d "%~dp0"

set PY=
if exist "%~dp0runtime\python\python.exe" set PY="%~dp0runtime\python\python.exe"
if not defined PY (
  python --version >nul 2>&1
  if not errorlevel 1 set PY=python
)
if not defined PY (
  python3 --version >nul 2>&1
  if not errorlevel 1 set PY=python3
)
if not defined PY (
  py --version >nul 2>&1
  if not errorlevel 1 set PY=py
)
if not defined PY (
  echo [ERROR] Python 3 not found in PATH. Please install Python 3 first.
  echo         https://www.python.org/downloads/
  pause
  exit /b 1
)

set PYTHONIOENCODING=utf-8
%PY% install.py %*
echo.
pause
