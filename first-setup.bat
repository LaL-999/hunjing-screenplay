@echo off
REM ============================================================
REM 浑晶 · 剧创态 — 首次设置脚本(Windows)
REM ============================================================
REM 做 3 件事:
REM   1. backend:复制 .env.example → .env(若不存在)
REM   2. backend:pip install -r requirements.txt(用全局 Python)
REM   3. frontend:npm install
REM
REM 完成后双击 start-dev.bat 启动两个服务。
REM ============================================================

title Hunjing-Screenplay First-Setup

echo.
echo ============================================================
echo   浑晶 · 剧创态 — First Setup
echo ============================================================
echo.

REM ---- 1. 创建 .env(若不存在)----
if not exist "%~dp0backend\.env" (
    echo [1/3] Creating backend\.env from .env.example...
    copy "%~dp0backend\.env.example" "%~dp0backend\.env" >nul
    echo       OK - backend\.env created
    echo       ^^^ Please edit backend\.env and fill DEEPSEEK_API_KEY
    echo           ^(or skip - non-LLM features will still work^)
) else (
    echo [1/3] backend\.env already exists - skip
)
echo.

REM ---- 2. backend 依赖 ----
echo [2/3] Installing Python dependencies...
echo       This may take a minute on first run.
cd /d "%~dp0backend"
python -m pip install -q -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERROR] pip install failed - check error above
    echo You may need: python -m pip install --upgrade pip
    cd /d "%~dp0"
    pause
    exit /b 1
)
echo       OK - Python dependencies installed
cd /d "%~dp0"
echo.

REM ---- 3. frontend 依赖 ----
echo [3/3] Installing frontend npm dependencies...
echo       This will take ~1-2 minutes on first run.
cd /d "%~dp0frontend"
call npm install
if errorlevel 1 (
    echo.
    echo [ERROR] npm install failed - check error above
    echo Make sure Node.js 18+ is installed: https://nodejs.org/
    cd /d "%~dp0"
    pause
    exit /b 1
)
echo       OK - npm dependencies installed
cd /d "%~dp0"
echo.

echo ============================================================
echo   Setup complete!
echo.
echo   Next steps:
echo     1. ^(Optional^) Edit backend\.env to fill DEEPSEEK_API_KEY
echo     2. Double-click start-dev.bat to launch
echo        - Backend  : http://localhost:8002
echo        - Frontend : http://localhost:5174
echo ============================================================
echo.
pause
