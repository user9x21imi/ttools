@echo off
cd /d "%~dp0"
py -3 install-local.py
if errorlevel 1 (
  echo Installation failed. Python 3.11+ and an Internet connection are required.
  pause
  exit /b 1
)
pause
