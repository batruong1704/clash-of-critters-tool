@echo off
setlocal
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"

call :ensure
if errorlevel 1 exit /b 1
"%PY%" main.py
if errorlevel 1 pause
exit /b 0

:ensure
if exist "%PY%" (
    "%PY%" -c "import cv2,numpy,PIL" >nul 2>&1
    if not errorlevel 1 exit /b 0
    "%PY%" -c "import sys" >nul 2>&1
    if errorlevel 1 rmdir /s /q "%~dp0.venv"
)
if not exist "%PY%" (
    py -3 -m venv "%~dp0.venv"
    if errorlevel 1 python -m venv "%~dp0.venv"
    if errorlevel 1 (
        echo Khong tao duoc .venv. Cai Python 3 roi mo lai run.bat.
        pause
        exit /b 1
    )
)
"%PY%" -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo Cai thu vien that bai. Kiem tra mang roi mo lai run.bat.
    pause
    exit /b 1
)
exit /b 0
