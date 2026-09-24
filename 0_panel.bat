@echo off
REM WorkBuddy2API control panel launcher (ASCII only - do not add Chinese here)
REM GBK console would mangle UTF-8 Chinese in .bat files, so all text lives in control_panel.py
chcp 65001 >nul
cd /d "%~dp0"

set PY=
REM 1) 优先用项目自带的绿色 Python（runtime/python），没环境也能跑
if exist "%~dp0runtime\python\python.exe" set PY="%~dp0runtime\python\python.exe"
REM 2) 否则退回系统 Python
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
  echo [ERROR] No usable Python found.
  echo         Project runtime missing AND Python 3 not in PATH.
  echo         https://www.python.org/downloads/
  pause
  exit /b 1
)

set PYTHONIOENCODING=utf-8
title WorkBuddy2API Control Panel
%PY% control_panel.py %*
echo.
pause
