@echo off
setlocal
title Copypan Stop All

echo ============================================================
echo Copypan Stop Script
echo ============================================================
echo.

echo [1/5] Stopping Nginx...
taskkill /f /im nginx.exe >nul 2>&1
if errorlevel 1 (
    echo [INFO] Nginx not running.
) else (
    echo [OK] Nginx stopped.
)
echo.

echo [2/5] Stopping Redis...
where docker >nul 2>&1
set "HAS_DOCKER=1"
if errorlevel 1 (
    set "HAS_DOCKER=0"
    echo [WARN] docker command not found, skip Redis/Neo4j/Elasticsearch stop.
) else (
    docker stop redis >nul 2>&1
    if errorlevel 1 (
        echo [INFO] Redis not running.
    ) else (
        echo [OK] Redis stopped.
    )
)
echo.

echo [3/5] Stopping backend...
taskkill /f /fi "WINDOWTITLE eq Copypan Backend*" >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
    taskkill /f /pid %%a >nul 2>&1
)
echo [OK] Backend stop commands executed.
echo.

if "%HAS_DOCKER%"=="1" (
    echo [4/5] Stopping Neo4j...
    docker stop neo4j >nul 2>&1
    if errorlevel 1 (
        echo [INFO] Neo4j not running.
    ) else (
        echo [OK] Neo4j stopped.
    )
    echo.

    echo [5/5] Stopping Elasticsearch8...
    docker stop elasticsearch8 >nul 2>&1
    if errorlevel 1 (
        echo [INFO] Elasticsearch8 not running.
    ) else (
        echo [OK] Elasticsearch8 stopped.
    )
    echo.
)

echo ============================================================
echo Stop completed.
echo ============================================================
pause