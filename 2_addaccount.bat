@echo off
REM Add CodeBuddy account launcher (ASCII only - do not add Chinese here)
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
  pause
  exit /b 1
)

set PYTHONIOENCODING=utf-8
%PY% addaccount.py
echo.
pause
