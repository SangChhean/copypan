@echo off
chcp 65001 >nul
title Copypan 服务状态

echo ============================================================
echo              Copypan 服务状态
echo ============================================================
echo.

echo [Elasticsearch]
docker ps --filter "name=elasticsearch" --format "{{.Status}}" | find "Up" >nul
if %errorlevel% equ 0 (
    echo ✓ 运行中
    curl -s http://localhost:9200 >nul 2>&1
    if %errorlevel% equ 0 (
        echo   可访问: http://localhost:9200
    )
) else (
    echo ❌ 未运行
)
echo.

echo [Kibana]
docker ps --filter "name=kibana" --format "{{.Status}}" | find "Up" >nul
if %errorlevel% equ 0 (
    echo ✓ 运行中
    echo   可访问: http://localhost:5601
) else (
    echo ❌ 未运行
)
echo.

echo [后端服务]
tasklist /fi "imagename eq python.exe" | find "python.exe" >nul
if %errorlevel% equ 0 (
    echo ✓ 运行中
    curl -s http://localhost:8000 >nul 2>&1
    if %errorlevel% equ 0 (
        echo   可访问: http://localhost:8000
    )
) else (
    echo ❌ 未运行
)
echo.

echo [Nginx]
tasklist /fi "imagename eq nginx.exe" | find "nginx.exe" >nul
if %errorlevel% equ 0 (
    echo ✓ 运行中
    echo   可访问: http://localhost
) else (
    echo ❌ 未运行
)
echo.

echo ============================================================
echo.
pause