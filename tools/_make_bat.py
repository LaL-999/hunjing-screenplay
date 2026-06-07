"""Generate start.bat with GBK encoding and zero escape issues."""
from pathlib import Path

# raw string — every backslash is literal
content = r"""@echo off
REM ============================================================
REM Hunjing-Screenplay - One-Click Launcher
REM ============================================================

title Hunjing-Screenplay Launcher

echo.
echo  ============================================================
echo                     HUNJING-SCREENPLAY
echo                  AI Novel-to-Screenplay Tool
echo                     One-Click Launcher
echo  ============================================================
echo.
echo   Backend  : http://localhost:8003
echo   Frontend : http://localhost:5174  (will auto-open in browser)
echo.
echo  ------------------------------------------------------------
echo.

REM === Step 1: env check ===
echo  [1/5] Checking runtime environment...

REM Prefer py launcher (skips broken msys/mingw python in PATH)
where py >nul 2>&1
if errorlevel 1 (
    echo.
    echo   ERROR: Python Launcher ^(py^) not found
    echo   Please install official Python from https://www.python.org/downloads/
    echo   The installer includes py launcher and avoids PATH conflicts
    echo.
    pause
    exit /b 1
)

py -3 --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo   ERROR: Python 3 not found via py launcher
    echo   Please install Python 3.11+: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('py -3 --version 2^>^&1') do set PY_VER=%%i
echo         %PY_VER%

node --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo   ERROR: Node.js not found
    echo   Please install Node.js 18+: https://nodejs.org/
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('node --version 2^>^&1') do set NODE_VER=%%i
echo         Node.js %NODE_VER%
echo.

REM === Step 2: config check ===
echo  [2/5] Checking config files...

if not exist "%~dp0backend\app\main.py" (
    echo.
    echo   ERROR: backend\app\main.py missing
    echo   Please run this script in the project root directory
    echo.
    pause
    exit /b 1
)

if not exist "%~dp0backend\.env" (
    if exist "%~dp0backend\.env.example" (
        echo         backend\.env missing - copying from .env.example
        copy "%~dp0backend\.env.example" "%~dp0backend\.env" >nul
        echo         [TIP] To enable LLM features, edit backend\.env
        echo               and fill DEEPSEEK_API_KEY ^(optional^)
    ) else (
        echo   WARN: backend\.env and .env.example both missing
        echo         LLM features disabled, other features still work
    )
) else (
    echo         backend\.env  OK
)
echo.

REM === Step 3: python deps ===
echo  [3/5] Checking backend dependencies...

py -3 -c "import fastapi" >nul 2>&1
if errorlevel 1 (
    echo         First run - installing backend deps ^(~1 min^)...
    pushd "%~dp0backend"
    py -3 -m pip install -q -r requirements.txt
    if errorlevel 1 (
        echo.
        echo   ERROR: pip install failed
        echo   Try: cd backend ^&^& py -3 -m pip install -r requirements.txt
        echo.
        popd
        pause
        exit /b 1
    )
    popd
    echo         Backend deps installed  OK
) else (
    echo         FastAPI ready  OK
)
echo.

REM === Step 4: node deps ===
echo  [4/5] Checking frontend dependencies...

if not exist "%~dp0frontend\node_modules" (
    echo         First run - installing frontend deps ^(~1-2 min^)...
    pushd "%~dp0frontend"
    call npm install --silent
    if errorlevel 1 (
        echo.
        echo   ERROR: npm install failed
        echo   Try: cd frontend ^&^& npm install
        echo.
        popd
        pause
        exit /b 1
    )
    popd
    echo         Frontend deps installed  OK
) else (
    echo         node_modules ready  OK
)
echo.

REM === Step 5: launch + wait + open browser ===
echo  [5/5] Launching services...
echo.

echo         Starting backend on 8003...
start "Hunjing-Screenplay Backend :8003" cmd /k "cd /d %~dp0backend && py -3 -m uvicorn app.main:app --reload --port 8003"

echo         Starting frontend on 5174...
start "Hunjing-Screenplay Frontend :5174" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo  ------------------------------------------------------------
echo         Waiting for backend to be ready...
echo  ------------------------------------------------------------

set /a TRIES=0
:HEALTHCHECK
set /a TRIES+=1
if %TRIES% GTR 30 (
    echo.
    echo   WARN: backend startup timeout, opening browser anyway
    echo         check the backend window for error messages
    goto OPEN_BROWSER
)
timeout /t 1 /nobreak >nul
curl -s -f http://localhost:8003/health >nul 2>&1
if errorlevel 1 (
    <nul set /p="."
    goto HEALTHCHECK
)
echo.
echo.
echo         Backend ready  OK

timeout /t 2 /nobreak >nul

:OPEN_BROWSER
echo         Opening browser  OK
start "" "http://localhost:5174"

echo.
echo  ============================================================
echo                  Launch complete - all running
echo  ============================================================
echo.
echo   Frontend : http://localhost:5174
echo   API docs : http://localhost:8003/docs
echo.
echo   To stop: close the two "Hunjing-Screenplay ..." windows
echo.
echo  ============================================================
echo.
echo   ^(Press any key to close this launcher - services keep running^)
pause >nul
"""

# Ensure CRLF line endings (Windows batch)
content_crlf = content.replace("\r\n", "\n").replace("\n", "\r\n")

path = Path(__file__).parent.parent / "start.bat"
with open(path, "w", encoding="gbk", newline="") as f:
    f.write(content_crlf)

# Verify zero BELL chars + zero unexpected newlines
with open(path, "rb") as f:
    raw = f.read()

bell_count = raw.count(bytes([7]))
nul_count = raw.count(bytes([0]))
print(f"File: {path}")
print(f"Size: {len(raw)} bytes")
print(f"BELL chars: {bell_count} (expected 0)")
print(f"NUL chars: {nul_count} (expected 0)")

# Specific path checks
checks = [
    rb"backend\app\main.py",
    rb"backend\.env",
    rb"frontend\node_modules",
    rb"py -3 --version",
    rb"py -3 -m uvicorn",
    rb">nul",
]
for c in checks:
    print(f"  {c.decode('ascii', errors='replace')}: {c in raw}")
