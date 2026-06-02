@echo off
setlocal EnableExtensions
title Copypan QA Start
if /i "%~1"=="nopause" set "NOPAUSE=1"

cd /d "%~dp0"
set "PROJECT_DIR=%CD%"
set "FRONTEND_QA=%PROJECT_DIR%\front_qa"

echo ============================================================
echo Copypan QA start - back_qa + front_qa
echo ============================================================
echo Requires ES, Redis, Neo4j running (e.g. start_all.bat first).
echo.

where docker >nul 2>&1
if not errorlevel 1 (
    echo [deps] Docker found, checking containers...
    docker ps --filter "name=elasticsearch8" --filter "status=running" --format "{{.Names}}" 2>nul | findstr /i "^elasticsearch8$" >nul
    if errorlevel 1 (
        echo [WARN] elasticsearch8 not running
    ) else (
        echo [OK] elasticsearch8 running
    )
    docker ps --filter "name=redis" --filter "status=running" --format "{{.Names}}" 2>nul | findstr /i "^redis$" >nul
    if errorlevel 1 (
        echo [WARN] redis not running
    ) else (
        echo [OK] redis running
    )
    docker ps --filter "name=neo4j" --filter "status=running" --format "{{.Names}}" 2>nul | findstr /i "^neo4j$" >nul
    if errorlevel 1 (
        echo [WARN] neo4j not running
    ) else (
        echo [OK] neo4j running
    )
    echo.
) else (
    echo [WARN] docker not in PATH, skip container checks
    echo.
)

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] python not in PATH
    if not defined NOPAUSE pause
    exit /b 1
)

echo [1/2] Starting back_qa in new window :8001 ...
start "QA Backend" cmd /k "cd /d %PROJECT_DIR% && set PYTHONIOENCODING=utf-8 && echo QA Backend http://127.0.0.1:8001 && python -m uvicorn back_qa.main:app --host 127.0.0.1 --port 8001"
echo [OK] Backend window started
ping 127.0.0.1 -n 3 >nul
echo.

where npm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] npm not in PATH
    if not defined NOPAUSE pause
    exit /b 1
)

echo [2/2] Starting front_qa Vite in new window :5174 ...
if not exist "%FRONTEND_QA%\package.json" (
    echo [ERROR] Missing %FRONTEND_QA%\package.json
    if not defined NOPAUSE pause
    exit /b 1
)
if not exist "%FRONTEND_QA%\node_modules\vite\bin\vite.js" (
    echo Installing front_qa dependencies...
    if exist "%FRONTEND_QA%\package-lock.json" (
        start "QA Frontend Install" cmd /k "cd /d %FRONTEND_QA% && npm ci"
    ) else (
        start "QA Frontend Install" cmd /k "cd /d %FRONTEND_QA% && npm install"
    )
    echo [INFO] Please wait for install window to finish, then rerun start_qa.bat.
    if not defined NOPAUSE pause
    exit /b 1
)
start "QA Frontend" cmd /k "cd /d %FRONTEND_QA% && echo QA Frontend http://127.0.0.1:5174 && npm run dev -- --host 127.0.0.1 --port 5174"
echo [OK] Frontend window started
ping 127.0.0.1 -n 3 >nul
echo.

if not defined NOPAUSE (
    echo Opening browser...
    start http://127.0.0.1:5174/
    echo.
)

echo ============================================================
echo Ready.
echo - API:     http://127.0.0.1:8001   /api/qa/liveness
echo - Web:     http://127.0.0.1:5174   admin: #/admin
echo ============================================================
echo Stop: run stop_qa.bat
echo.
if not defined NOPAUSE pause
