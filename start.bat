@echo off
setlocal enabledelayedexpansion
title Paper Vision - Question Bank Workbench

set "BASE_DIR=%~dp0"
set "CONFIG_FILE=%BASE_DIR%config.ini"

echo.
echo  ========================================
echo    Paper Vision - Question Bank v1.0
echo  ========================================
echo.

:: ========================================================
::  1. First run - configure database
:: ========================================================
if not exist "%CONFIG_FILE%" (
    echo  --- First Run - Configure MySQL ---
    echo.
    echo  Please install MySQL, create database,
    echo  and import pb_data.sql before continuing.
    echo  ----------------------------------------
    set /p "DB_HOST=MySQL host [localhost]: "
    if "!DB_HOST!"=="" set "DB_HOST=localhost"
    set /p "DB_PORT=MySQL port [3306]: "
    if "!DB_PORT!"=="" set "DB_PORT=3306"
    set /p "DB_NAME=Database name [pb_data]: "
    if "!DB_NAME!"=="" set "DB_NAME=pb_data"
    set /p "DB_USER=Username [root]: "
    if "!DB_USER!"=="" set "DB_USER=root"
    set /p "DB_PASS=Password: "
    (
        echo DB_HOST=!DB_HOST!
        echo DB_PORT=!DB_PORT!
        echo DB_NAME=!DB_NAME!
        echo DB_USER=!DB_USER!
        echo DB_PASS=!DB_PASS!
    ) > "%CONFIG_FILE%"
    echo.
    echo  Config saved.
    echo.
)

:: ========================================================
::  2. Load config
:: ========================================================
for /f "tokens=1,* delims==" %%a in ('type "%CONFIG_FILE%"') do set "%%a=%%b"

:: ========================================================
::  3. Check MySQL connectivity
:: ========================================================
echo [Check] MySQL %DB_HOST%:%DB_PORT% ...
powershell -Command "try{$t=New-Object Net.Sockets.TcpClient;$t.Connect('%DB_HOST%',%DB_PORT%);$t.Close();exit 0}catch{exit 1}" 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Cannot connect to MySQL - please make sure MySQL is installed and running
    pause & exit /b 1
)
echo   OK

:: ========================================================
::  4. Check bundled JRE
:: ========================================================
set "JAVA=%BASE_DIR%jre\bin\java.exe"
if not exist "%JAVA%" (
    echo [ERROR] Missing jre\ folder - please re-extract the full package
    pause & exit /b 1
)
echo [Check] Bundled JRE OK

:: ========================================================
::  5. Python - auto-install if missing
:: ========================================================
set "PYTHON=%BASE_DIR%python\python.exe"
if not exist "%PYTHON%" (
    echo.
    echo ============================================
    echo   First run: installing OCR engine (~3.5 GB)
    echo   One-time setup, requires internet
    echo ============================================
    echo.
    pause
    call "%BASE_DIR%setup-python.bat"
    if not exist "%PYTHON%" (
        echo [ERROR] OCR setup failed
        pause & exit /b 1
    )
    echo [Check] Python OCR OK
) else (
    echo [Check] Bundled Python OK
)

:: ========================================================
::  6. Start OCR service
:: ========================================================
echo.
echo [Start] OCR recognition service ...
set "OCR_DEVICE=cpu"
start "OCR-Service" /MIN cmd /c ""%PYTHON%" -u "%BASE_DIR%ocr-service\app.py""
echo   OCR  -> http://localhost:8000

:: ========================================================
::  7. Start Java backend
:: ========================================================
echo [Start] Backend service ...
set "DB_URL=jdbc:mysql://%DB_HOST%:%DB_PORT%/%DB_NAME%?useUnicode=true&characterEncoding=utf8&serverTimezone=Asia/Shanghai&sslMode=DISABLED"
set "PAPER_VISION_DB_URL=%DB_URL%"
set "PAPER_VISION_DB_USERNAME=%DB_USER%"
set "PAPER_VISION_DB_PASSWORD=%DB_PASS%"
start "PaperVision" /MIN cmd /c ""%JAVA%" -jar "%BASE_DIR%paper-vision-api.jar""
echo   Backend -> http://localhost:8080

:: ========================================================
::  8. Wait for backend to be ready
:: ========================================================
echo [Wait] Backend starting ...
set /a RETRIES=0
:wait_loop
powershell -Command "try{$r=Invoke-WebRequest -Uri 'http://localhost:8080/api/question-bank/health' -UseBasicParsing -TimeoutSec 2;exit 0}catch{exit 1}" 2>nul
if %errorlevel% equ 0 goto :ready
set /a RETRIES+=1
if %RETRIES% geq 30 (
    echo [ERROR] Backend startup timed out
    goto :cleanup
)
timeout /t 2 /nobreak >nul
goto :wait_loop

:ready
echo.
echo ========================================
echo   All services ready!
echo   Opening browser: http://localhost:8080
echo   Close this window to stop all services
echo ========================================
start http://localhost:8080
pause

:cleanup
echo [Stop] Shutting down services ...
taskkill /fi "WINDOWTITLE eq OCR-Service*" /f >nul 2>&1
taskkill /fi "WINDOWTITLE eq PaperVision*" /f >nul 2>&1
echo   Done
exit /b 0
