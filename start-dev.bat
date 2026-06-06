@echo off
REM ============================================================
REM 浑晶 · 剧创态 — 一键开发环境启动(Windows)
REM   backend:  http://localhost:8002
REM   frontend: http://localhost:5174
REM ============================================================

title 浑晶剧创态 Dev Launcher

echo.
echo ============================================================
echo   浑晶 · 剧创态 Dev — Starting...
echo.
echo   Backend  : http://localhost:8002
echo   Frontend : http://localhost:5174
echo.
echo   Two services will run in separate child windows.
echo   Close a child window to stop that service.
echo ============================================================
echo.

REM ---- sanity check ----
if not exist "%~dp0backend\app\main.py" (
    echo [ERROR] backend\app\main.py not found
    pause
    exit /b 1
)
if not exist "%~dp0backend\.env" (
    echo [WARN] backend\.env not found
    echo Please copy backend\.env.example to backend\.env and fill DEEPSEEK_API_KEY
    echo Continuing anyway - backend will fail to start without it.
    timeout /t 3 >nul
)

REM ---- start backend ----
echo Starting backend...
start "hunjing-screenplay backend (8002)" cmd /k "cd /d %~dp0backend && uvicorn app.main:app --reload --port 8002"

REM ---- start frontend ----
echo Starting frontend...
start "hunjing-screenplay frontend (5174)" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo Both services launched. Check the two new windows for logs.
echo Press any key to close this launcher window.
pause >nul
