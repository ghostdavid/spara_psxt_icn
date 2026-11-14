@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -File check_zones.ps1
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -B -m PyInstaller --clean --noconfirm main.spec
if errorlevel 1 exit /b 1
powershell -NoProfile -File check_zones.ps1
if errorlevel 1 exit /b 1
