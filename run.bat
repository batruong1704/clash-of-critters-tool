@echo off
setlocal
cd /d "%~dp0checking-mvp"
set "PY=.venv\Scripts\python.exe"

call :ensure
if errorlevel 1 exit /b 1
"%PY%" main.py
if errorlevel 1 pause
exit /b 0

:ensure
if not exist "%PY%" goto create
call :base_ok
if errorlevel 1 goto recreate
"%PY%" -c "import cv2,numpy,PIL,sv_ttk" >nul 2>&1
if not errorlevel 1 exit /b 0
goto pip

:recreate
echo Moi truong Python cu tro ve may khac. Dang tao lai...
call :discard
if errorlevel 1 exit /b 1

:create
py -3 -m venv .venv
if errorlevel 1 python -m venv .venv
if errorlevel 1 (
    echo Khong tao duoc .venv. Cai Python 3 roi mo lai run.bat.
    pause
    exit /b 1
)

:pip
"%PY%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo Cai thu vien that bai. Kiem tra mang roi mo lai run.bat.
    pause
    exit /b 1
)
exit /b 0

:base_ok
if not exist ".venv\pyvenv.cfg" exit /b 1
set "BASE="
for /f "usebackq tokens=1,* delims==" %%A in (".venv\pyvenv.cfg") do (
    set "KEY=%%A"
    set "VAL=%%B"
    call :take_home
)
if not defined BASE exit /b 1
if not exist "%BASE%\python.exe" exit /b 1
exit /b 0

:take_home
set "KEY=%KEY: =%"
if /i not "%KEY%"=="home" exit /b 0
set "BASE=%VAL%"
if "%BASE:~0,1%"==" " set "BASE=%BASE:~1%"
exit /b 0

:discard
rmdir /s /q ".venv"
if not exist ".venv" exit /b 0
ren ".venv" ".venv.cu.%RANDOM%"
if exist ".venv" (
    echo Khong xoa duoc .venv cu. Dong cac cua so dang mo thu muc nay roi chay lai run.bat.
    pause
    exit /b 1
)
exit /b 0
