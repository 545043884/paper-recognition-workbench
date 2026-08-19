@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ============================================
echo   试卷识别工作台 - 构建打包脚本
echo ============================================
echo.

set "PROJECT_DIR=%~dp0"
set "DIST_DIR=%PROJECT_DIR%dist-package"

:: ---- 1. Build frontend ----
echo [1/4] 构建前端...
cd /d "%PROJECT_DIR%frontend"
call npm run build 2>&1 | findstr /V "KaTeX"
if %errorlevel% neq 0 (
    echo 前端构建失败!
    exit /b 1
)
echo   前端构建完成

:: Copy to static
if exist "%PROJECT_DIR%src\main\resources\static" (
    rmdir /s /q "%PROJECT_DIR%src\main\resources\static"
)
mkdir "%PROJECT_DIR%src\main\resources\static"
xcopy /e /q "%PROJECT_DIR%frontend\dist\*" "%PROJECT_DIR%src\main\resources\static\"
echo   前端已复制到 static/

:: ---- 2. Build Java backend ----
echo.
echo [2/4] 编译 Java 后端...
cd /d "%PROJECT_DIR%"
call mvn -q package -DskipTests 2>&1
if %errorlevel% neq 0 (
    echo Java 编译失败!
    exit /b 1
)
echo   Java 编译完成

:: ---- 3. Prepare distribution directory ----
echo.
echo [3/4] 准备发布目录...
if exist "%DIST_DIR%" rmdir /s /q "%DIST_DIR%"
mkdir "%DIST_DIR%"
mkdir "%DIST_DIR%\ocr-service"
mkdir "%DIST_DIR%\uploads\graphs"

:: Copy JAR
copy /y "%PROJECT_DIR%target\paper-vision-api-0.1.0.jar" "%DIST_DIR%\paper-vision-api.jar" >nul
echo   JAR 已复制

:: Copy OCR service
copy /y "%PROJECT_DIR%ocr-service\app.py" "%DIST_DIR%\ocr-service\app.py" >nul
echo   OCR 服务已复制

:: ---- 4. Set up Python environment ----
echo.
echo [4/4] 设置 Python OCR 环境...

:: Check for system Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo   [警告] 未找到 Python，正在下载嵌入式 Python...

    :: Download Python embeddable
    set "PYTHON_ZIP=%TEMP%\python-embed.zip"
    set "PYTHON_URL=https://www.python.org/ftp/python/3.10.11/python-3.10.11-embed-amd64.zip"

    powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '!PYTHON_URL!' -OutFile '!PYTHON_ZIP!'}" 2>&1
    if !errorlevel! neq 0 (
        echo   [警告] Python 下载失败，请手动安装 Python 3.10+
        echo   下载地址: https://www.python.org/downloads/
    ) else (
        mkdir "%DIST_DIR%\python"
        powershell -Command "Expand-Archive -Path '!PYTHON_ZIP!' -DestinationPath '%DIST_DIR%\python'" 2>&1
        del "!PYTHON_ZIP!"

        :: Enable pip for embedded Python
        echo import site >> "%DIST_DIR%\python\python310._pth"

        :: Install pip
        "%DIST_DIR%\python\python.exe" -m ensurepip 2>&1
        "%DIST_DIR%\python\python.exe" -m pip install --upgrade pip -q 2>&1

        :: Install OCR dependencies (CPU version)
        echo   正在安装 PaddleOCR CPU 版（可能需要几分钟）...
        "%DIST_DIR%\python\python.exe" -m pip install paddlepaddle==3.3.0 paddleocr==3.7.0 paddlex[ocr]==3.7.2 fastapi==0.141.1 uvicorn[standard]==0.52.0 python-multipart==0.0.32 -q 2>&1

        echo   Python OCR 环境安装完成
    )
) else (
    echo   检测到系统 Python，请在目标机器上手动运行:
    echo   pip install -r ocr-service\requirements-cpu.txt
)

echo.
echo ============================================
echo   构建完成！
echo   发布目录: %DIST_DIR%
echo ============================================
echo.
echo 将整个 dist-package 目录复制到目标电脑，然后双击 start.bat 即可使用。
echo.
pause
