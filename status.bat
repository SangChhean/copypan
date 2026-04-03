@echo off
setlocal
title Copypan Status

echo ============================================================
echo Copypan Service Status
echo ============================================================
echo.

where docker >nul 2>&1
if errorlevel 1 (
    echo [WARN] docker command not found. Container status unavailable.
) else (
    echo [Elasticsearch8]
    docker ps --filter "name=elasticsearch8" --filter "status=running" --format "{{.Names}}" | findstr /i "^elasticsearch8$" >nul
    if errorlevel 1 (
        echo [DOWN]
    ) else (
        echo [UP]
        curl -s http://localhost:9200 >nul 2>&1 && echo URL: http://localhost:9200
    )
    echo.

    echo [Redis]
    docker ps --filter "name=redis" --filter "status=running" --format "{{.Names}}" | findstr /i "^redis$" >nul
    if errorlevel 1 (
        echo [DOWN]
    ) else (
        echo [UP]
        echo URL: localhost:6379
    )
    echo.

    echo [Neo4j]
    docker ps --filter "name=neo4j" --filter "status=running" --format "{{.Names}}" | findstr /i "^neo4j$" >nul
    if errorlevel 1 (
        echo [DOWN]
    ) else (
        echo [UP]
        echo URL: http://localhost:7474
        echo BOLT: localhost:7687
    )
    echo.
)

echo [Backend API]
tasklist /fi "imagename eq python.exe" | findstr /i "python.exe" >nul
if errorlevel 1 (
    echo [DOWN]
) else (
    echo [UP]
    curl -s http://localhost:8000 >nul 2>&1 && echo URL: http://localhost:8000
)
echo.

echo [Nginx]
tasklist /fi "imagename eq nginx.exe" | findstr /i "nginx.exe" >nul
if errorlevel 1 (
    echo [DOWN]
) else (
    echo [UP]
    echo URL: http://localhost
)
echo.

echo ============================================================
pause