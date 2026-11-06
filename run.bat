@echo off
setlocal
cd /d "%~dp0checking-mvp"
set "PY=.venv\Scripts\python.exe"
set "PYW=.venv\Scripts\pythonw.exe"

call :ensure
if errorlevel 1 exit /b 1
if not exist "%PYW%" set "PYW=%PY%"
start "" "%PYW%" main.py
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
call :python_cmd
if defined PYCMD goto make_venv
echo Chua co Python 3.11 tro len.
echo Dang cai Python 3.13 cho tai khoan nay. Can mang, co the mat vai phut.
call :install_python
if errorlevel 1 (
    echo Khong cai duoc Python. Cai Python 3.13 roi mo lai run.bat.
    pause
    exit /b 1
)
call :python_cmd
if not defined PYCMD (
    echo Da cai Python nhung cua so nay chua thay. Dong cua so roi mo lai run.bat.
    pause
    exit /b 1
)

:make_venv
echo Dang tao moi truong Python...
"%PYCMD%" %PYARGS% -m venv .venv
if errorlevel 1 (
    echo Khong tao duoc .venv.
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

:python_cmd
set "PYCMD="
set "PYARGS="
set "BESTVER=0"
call :take_py
for /d %%D in ("%LocalAppData%\Programs\Python\Python3*") do call :take "%%D\python.exe"
for /d %%D in ("%ProgramFiles%\Python3*") do call :take "%%D\python.exe"
for /f "delims=" %%P in ('where python 2^>nul') do call :take "%%P"
if %BESTVER% GEQ 311 exit /b 0
set "PYCMD="
set "PYARGS="
exit /b 0

:take
set "CAND=%~1"
if not exist "%CAND%" exit /b 0
echo %CAND%| find /i "\WindowsApps\" >nul && exit /b 0
"%CAND%" -c "import sys; print(sys.version_info[0]*100+sys.version_info[1])" > "%TEMP%\coc-pyver.txt" 2>nul
if errorlevel 1 exit /b 0
set "VER="
set /p VER=<"%TEMP%\coc-pyver.txt"
if not defined VER exit /b 0
if %VER% LSS 311 exit /b 0
if %VER% LEQ %BESTVER% exit /b 0
set "BESTVER=%VER%"
set "PYCMD=%CAND%"
set "PYARGS="
exit /b 0

:take_py
py -3 -c "import sys; print(sys.version_info[0]*100+sys.version_info[1])" > "%TEMP%\coc-pyver.txt" 2>nul
if errorlevel 1 exit /b 0
set "VER="
set /p VER=<"%TEMP%\coc-pyver.txt"
if not defined VER exit /b 0
if %VER% LSS 311 exit /b 0
if %VER% LEQ %BESTVER% exit /b 0
set "BESTVER=%VER%"
set "PYCMD=py"
set "PYARGS=-3"
exit /b 0

:install_python
where winget >nul 2>&1
if errorlevel 1 goto download_python
winget install --id Python.Python.3.13 -e --scope user --accept-package-agreements --accept-source-agreements --disable-interactivity
if not errorlevel 1 exit /b 0

:download_python
set "ARCH=%PROCESSOR_ARCHITECTURE%"
if defined PROCESSOR_ARCHITEW6432 set "ARCH=%PROCESSOR_ARCHITEW6432%"
set "PYARCH="
if /i "%ARCH%"=="AMD64" set "PYARCH=amd64"
if /i "%ARCH%"=="ARM64" set "PYARCH=arm64"
if not defined PYARCH (
    echo May nay khong phai Windows 64-bit.
    exit /b 1
)
set "SETUP=%TEMP%\python-3.13.17-%PYARCH%.exe"
echo Dang tai bo cai Python...
curl -fsSL -o "%SETUP%" "https://www.python.org/ftp/python/3.13.17/python-3.13.17-%PYARCH%.exe"
if errorlevel 1 exit /b 1
echo Dang cai Python...
"%SETUP%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_pip=1 Include_test=0 Include_doc=0 Shortcuts=0
if "%ERRORLEVEL%"=="0" exit /b 0
if "%ERRORLEVEL%"=="3010" exit /b 0
exit /b 1

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
