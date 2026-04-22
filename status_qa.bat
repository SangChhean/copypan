@echo off
setlocal EnableExtensions
title Copypan QA Status
if /i "%~1"=="nopause" set "NOPAUSE=1"

cd /d "%~dp0"

echo ============================================================
echo Copypan QA status
echo ============================================================
echo.

where docker >nul 2>&1
if not errorlevel 1 (
    echo [Elasticsearch8]
    docker ps --filter "name=elasticsearch8" --filter "status=running" --format "{{.Names}}" 2>nul | findstr /i "^elasticsearch8$" >nul
    if errorlevel 1 (
        echo [DOWN]
    ) else (
        echo [UP] http://localhost:9200
    )
    echo.

    echo [Redis]
    docker ps --filter "name=redis" --filter "status=running" --format "{{.Names}}" 2>nul | findstr /i "^redis$" >nul
    if errorlevel 1 (
        echo [DOWN]
    ) else (
        echo [UP] localhost:6379
    )
    echo.

    echo [Neo4j]
    docker ps --filter "name=neo4j" --filter "status=running" --format "{{.Names}}" 2>nul | findstr /i "^neo4j$" >nul
    if errorlevel 1 (
        echo [DOWN]
    ) else (
        echo [UP] http://localhost:7474
    )
    echo.
) else (
    echo [WARN] docker not in PATH, skip containers
    echo.
)

echo [back_qa :8001]
curl -s -o nul -w "HTTP %%{http_code}\n" http://127.0.0.1:8001/api/qa/liveness 2>nul
if errorlevel 1 (
    echo [DOWN] cannot connect http://127.0.0.1:8001
) else (
    echo [UP] http://127.0.0.1:8001/api/qa/liveness
)
echo.

echo [front_qa :5174]
curl -s -o nul -w "HTTP %%{http_code}\n" http://127.0.0.1:5174/ 2>nul
if errorlevel 1 (
    echo [DOWN] cannot connect http://127.0.0.1:5174
) else (
    echo [UP] http://127.0.0.1:5174/
)
echo.

echo ============================================================
if not defined NOPAUSE pause
