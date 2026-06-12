@echo off
setlocal EnableExtensions
title Copypan CN Start
if /i "%~1"=="nopause" set "NOPAUSE=1"

cd /d "%~dp0"
set "PROJECT_DIR=%CD%"

echo ============================================================
echo Copypan CN start - back_cn + front_cn (Phase 2)
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

echo [1/2] Starting back_cn in new window :8014 ...
start "CN Backend" cmd /k "cd /d %PROJECT_DIR% && set PYTHONIOENCODING=utf-8 && echo CN Backend http://127.0.0.1:8014 && python -m uvicorn back_cn.main:app --host 127.0.0.1 --port 8014"
echo [OK] Backend window started
ping 127.0.0.1 -n 3 >nul
echo.

set "FRONTEND_CN=%PROJECT_DIR%\front_cn"
where npm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] npm not in PATH
    if not defined NOPAUSE pause
    exit /b 1
)
echo [2/2] Starting front_cn Vite in new window :5176 ...
if not exist "%FRONTEND_CN%\package.json" (
    echo [ERROR] Missing %FRONTEND_CN%\package.json
    if not defined NOPAUSE pause
    exit /b 1
)
if not exist "%FRONTEND_CN%\node_modules\vite\bin\vite.js" (
    echo Installing front_cn dependencies...
    start "CN Frontend Install" cmd /k "cd /d %FRONTEND_CN% && npm install"
    echo [INFO] Please wait for install window to finish, then rerun start_cn.bat.
    if not defined NOPAUSE pause
    exit /b 1
)
start "CN Frontend" cmd /k "cd /d %FRONTEND_CN% && echo CN Frontend http://127.0.0.1:5176 && npm run dev -- --host 127.0.0.1 --port 5176"
echo [OK] Frontend window started
echo.

echo ============================================================
echo Ready.
echo - API:     http://127.0.0.1:8014   /api/cn/liveness
echo - Web:     http://127.0.0.1:5176
echo ============================================================
echo Stop: run stop_cn.bat
echo.
if not defined NOPAUSE pause
