# Paper Vision 一键启动脚本
# 首次运行会提示输入配置信息并保存到 .env 文件

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$EnvFile = Join-Path $ProjectRoot ".env"

# ============ 配置读写 ============

function Read-EnvFile {
    $config = @{}
    if (Test-Path $EnvFile) {
        Get-Content $EnvFile | ForEach-Object {
            $line = $_.Trim()
            if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
                $parts = $line -split "=", 2
                $config[$parts[0].Trim()] = $parts[1].Trim()
            }
        }
    }
    return $config
}

function Write-EnvFile($config) {
    $lines = @(
        "# Paper Vision 配置文件（自动生成，可手动修改）",
        "# 重新运行 start.ps1 时会读取此文件",
        ""
    )
    foreach ($key in $config.Keys | Sort-Object) {
        $lines += "$key=$($config[$key])"
    }
    $lines | Set-Content -Path $EnvFile -Encoding utf8
}

# ============ 首次运行交互 ============

function Initialize-Config {
    $config = Read-EnvFile

    # Docker-style .env files may only contain database settings. Supply the
    # local-development defaults so reusing that file never produces blank ports.
    if (-not $config["OCR_DEVICE"]) { $config["OCR_DEVICE"] = "gpu" }
    if (-not $config["OCR_PORT"]) { $config["OCR_PORT"] = "8000" }
    if (-not $config["PAPER_VISION_API_PORT"]) { $config["PAPER_VISION_API_PORT"] = "8080" }
    if (-not $config["FRONTEND_PORT"]) { $config["FRONTEND_PORT"] = "5174" }

    if ($config.Count -gt 0) {
        Write-Host ""
        Write-Host "已检测到配置文件 .env，当前配置：" -ForegroundColor Cyan
        Write-Host "  数据库地址: $($config['PAPER_VISION_DB_URL'])"
        Write-Host "  数据库用户: $($config['PAPER_VISION_DB_USERNAME'])"
        Write-Host "  OCR 设备:   $($config['OCR_DEVICE'])"
        Write-Host ""
        $reuse = Read-Host "使用现有配置启动？(Y/n)"
        if ($reuse -ne "n" -and $reuse -ne "N") {
            return $config
        }
    }

    Write-Host ""
    Write-Host "========== Paper Vision 初始化配置 ==========" -ForegroundColor Green
    Write-Host ""

    # 数据库配置
    Write-Host "[数据库配置]" -ForegroundColor Yellow
    $dbHost = Read-Host "MySQL 主机地址 (默认: localhost)"
    if (-not $dbHost) { $dbHost = "localhost" }
    $dbPort = Read-Host "MySQL 端口 (默认: 3306)"
    if (-not $dbPort) { $dbPort = "3306" }
    $dbName = Read-Host "数据库名 (默认: nine_question_bank)"
    if (-not $dbName) { $dbName = "nine_question_bank" }
    $dbUser = Read-Host "数据库用户名 (默认: root)"
    if (-not $dbUser) { $dbUser = "root" }
    $dbPass = Read-Host "数据库密码"

    # OCR 配置
    Write-Host ""
    Write-Host "[OCR 服务配置]" -ForegroundColor Yellow
    $device = Read-Host "OCR 运行设备 gpu/cpu (默认: gpu)"
    if ($device -ne "cpu") { $device = "gpu" }

    # 端口配置
    Write-Host ""
    Write-Host "[端口配置]" -ForegroundColor Yellow
    $ocrPort = Read-Host "OCR 服务端口 (默认: 8000)"
    if (-not $ocrPort) { $ocrPort = "8000" }
    $apiPort = Read-Host "后端 API 端口 (默认: 8080)"
    if (-not $apiPort) { $apiPort = "8080" }
    $frontendPort = Read-Host "前端端口 (默认: 5173)"
    if (-not $frontendPort) { $frontendPort = "5173" }

    $config = @{
        "PAPER_VISION_DB_URL"      = "jdbc:mysql://${dbHost}:${dbPort}/${dbName}?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=Asia/Shanghai"
        "PAPER_VISION_DB_USERNAME" = $dbUser
        "PAPER_VISION_DB_PASSWORD" = $dbPass
        "PAPER_VISION_API_PORT"    = $apiPort
        "OCR_DEVICE"               = $device
        "OCR_PORT"                 = $ocrPort
        "FRONTEND_PORT"            = $frontendPort
    }

    Write-EnvFile $config
    Write-Host ""
    Write-Host "配置已保存到 .env 文件" -ForegroundColor Green
    return $config
}

# ============ 环境检查 ============

function Test-Prerequisites {
    Write-Host ""
    Write-Host "检查运行环境..." -ForegroundColor Cyan

    # Python venv
    $venvPython = Join-Path $ProjectRoot ".venv-ocr\Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        Write-Host "[FAIL] 未找到 Python 虚拟环境: .venv-ocr" -ForegroundColor Red
        Write-Host "  请先运行: python -m venv .venv-ocr" -ForegroundColor Gray
        Write-Host "  然后安装依赖: .venv-ocr\Scripts\pip install -r ocr-service\requirements.txt" -ForegroundColor Gray
        return $false
    }
    Write-Host "  [OK] Python 虚拟环境" -ForegroundColor Green

    # Java
    try {
        $javaVersion = & java -version 2>&1 | Select-Object -First 1
        Write-Host "  [OK] Java: $javaVersion" -ForegroundColor Green
    } catch {
        Write-Host "  [FAIL] 未找到 Java，请安装 JDK 17+" -ForegroundColor Red
        return $false
    }

    # Maven
    $mvnw = Join-Path $ProjectRoot "mvnw.cmd"
    if (Test-Path $mvnw) {
        Write-Host "  [OK] Maven Wrapper" -ForegroundColor Green
    } else {
        try {
            $null = & mvn --version 2>&1
            Write-Host "  [OK] Maven (系统安装)" -ForegroundColor Green
        } catch {
            Write-Host "  [FAIL] 未找到 Maven，请安装 Maven 或添加 mvnw" -ForegroundColor Red
            return $false
        }
    }

    # Node.js
    try {
        $nodeVersion = & node --version 2>&1
        Write-Host "  [OK] Node.js: $nodeVersion" -ForegroundColor Green
    } catch {
        Write-Host "  [FAIL] 未找到 Node.js，请安装 Node.js 18+" -ForegroundColor Red
        return $false
    }

    return $true
}

# ============ 启动服务 ============

function Start-AllServices($config) {
    Write-Host ""
    Write-Host "========== 启动所有服务 ==========" -ForegroundColor Green

    $ocrPort = $config["OCR_PORT"]
    $apiPort = $config["PAPER_VISION_API_PORT"]
    $frontendPort = $config["FRONTEND_PORT"]

    # 设置环境变量
    $env:PAPER_VISION_DB_URL = $config["PAPER_VISION_DB_URL"]
    $env:PAPER_VISION_DB_USERNAME = $config["PAPER_VISION_DB_USERNAME"]
    $env:PAPER_VISION_DB_PASSWORD = $config["PAPER_VISION_DB_PASSWORD"]
    $env:PAPER_VISION_API_PORT = $apiPort
    $env:OCR_DEVICE = $config["OCR_DEVICE"]

    # 启动 OCR 服务
    Write-Host ""
    Write-Host "[1/3] 启动 OCR 服务 (端口 $ocrPort)..." -ForegroundColor Yellow
    $ocrArgs = "app:app --host 127.0.0.1 --port $ocrPort --app-dir `"$(Join-Path $ProjectRoot 'ocr-service')`""
    $ocrProcess = Start-Process -FilePath (Join-Path $ProjectRoot ".venv-ocr\Scripts\uvicorn.exe") `
        -ArgumentList $ocrArgs `
        -PassThru -NoNewWindow
    Write-Host "  OCR PID: $($ocrProcess.Id)" -ForegroundColor Gray

    # 启动 Spring Boot 后端
    Write-Host "[2/3] 启动后端 API (端口 $apiPort)..." -ForegroundColor Yellow
    $mvnw = Join-Path $ProjectRoot "mvnw.cmd"
    if (Test-Path $mvnw) {
        $mvnCmd = $mvnw
    } else {
        $mvnCmd = "mvn"
    }
    $apiProcess = Start-Process -FilePath $mvnCmd `
        -ArgumentList "spring-boot:run" `
        -WorkingDirectory $ProjectRoot `
        -PassThru -NoNewWindow
    Write-Host "  API PID: $($apiProcess.Id)" -ForegroundColor Gray

    # 启动前端
    Write-Host "[3/3] 启动前端 (端口 $frontendPort)..." -ForegroundColor Yellow
    $npmArgs = "run dev -- --port $frontendPort"
    $frontendProcess = Start-Process -FilePath "npm.cmd" `
        -ArgumentList $npmArgs `
        -WorkingDirectory (Join-Path $ProjectRoot "frontend") `
        -PassThru -NoNewWindow
    Write-Host "  Frontend PID: $($frontendProcess.Id)" -ForegroundColor Gray

    # 输出总览
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "  所有服务已启动！" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "  前端界面:    http://localhost:$frontendPort" -ForegroundColor White
    Write-Host "  OCR 服务:    http://localhost:$ocrPort/health" -ForegroundColor White
    Write-Host "  后端 API:    http://localhost:$apiPort" -ForegroundColor White
    Write-Host ""
    Write-Host "  按 Ctrl+C 停止所有服务" -ForegroundColor Gray
    Write-Host ""

    # 等待退出，Ctrl+C 时清理进程
    try {
        while ($true) {
            if ($ocrProcess.HasExited -and $apiProcess.HasExited -and $frontendProcess.HasExited) {
                Write-Host "所有服务已退出" -ForegroundColor Yellow
                break
            }
            Start-Sleep -Seconds 2
        }
    } finally {
        Write-Host ""
        Write-Host "正在停止服务..." -ForegroundColor Yellow
        foreach ($proc in @($ocrProcess, $apiProcess, $frontendProcess)) {
            if (-not $proc.HasExited) {
                try { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue } catch {}
            }
        }
        Write-Host "已停止所有服务" -ForegroundColor Green
    }
}

# ============ 主流程 ============

Write-Host ""
Write-Host "  ╔══════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "  ║   Paper Vision 试卷识别工作台        ║" -ForegroundColor Cyan
Write-Host "  ║   一键启动脚本                       ║" -ForegroundColor Cyan
Write-Host "  ╚══════════════════════════════════════╝" -ForegroundColor Cyan

$config = Initialize-Config

if (-not (Test-Prerequisites)) {
    Write-Host ""
    Write-Host "环境检查未通过，请安装缺失的依赖后重试。" -ForegroundColor Red
    Read-Host "按回车退出"
    exit 1
}

Start-AllServices $config
