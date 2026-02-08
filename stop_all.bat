@echo off
chcp 65001 >nul
title Copypan 停止服务

echo ============================================================
echo              Copypan 服务停止脚本
echo ============================================================
echo.

echo [1/5] 停止Nginx...
taskkill /f /im nginx.exe >nul 2>&1
if %errorlevel% equ 0 (
    echo ✓ Nginx已停止
) else (
    echo ⚠ Nginx未运行
)
echo.

echo [2/5] 停止 Redis...
docker stop redis >nul 2>&1
if %errorlevel% equ 0 (
    echo ✓ Redis 已停止
) else (
    echo ⚠ Redis 未运行
)
echo.

echo [3/5] 停止后端服务...
echo   提示：将停止所有 Python 进程（含 Copypan 后端）
for /f "tokens=2" %%a in ('tasklist /fi "imagename eq python.exe" /fo list ^| find "PID:"') do (
    taskkill /f /pid %%a >nul 2>&1
)
echo ✓ 后端服务已停止
echo.

echo [4/5] 停止Kibana...
docker stop kibana >nul 2>&1
if %errorlevel% equ 0 (
    echo ✓ Kibana已停止
) else (
    echo ⚠ Kibana未运行
)
echo.

echo [5/5] 停止Elasticsearch...
docker stop elasticsearch >nul 2>&1
if %errorlevel% equ 0 (
    echo ✓ Elasticsearch已停止
) else (
    echo ⚠ Elasticsearch未运行
)
echo.

echo ============================================================
echo              所有服务已停止
echo ============================================================
echo.
pause