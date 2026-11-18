@echo off
cd /d "%~dp0"
py -3 install-local.py --allow-partial
if errorlevel 1 (
  echo Installation failed. Python 3.10+ and an Internet connection are required.
  pause
  exit /b 1
)
pause
