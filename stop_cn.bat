@echo off
setlocal EnableExtensions
title Copypan CN Stop
if /i "%~1"=="nopause" set "NOPAUSE=1"

echo ============================================================
echo Copypan CN stop
echo ============================================================
echo.

echo [1/2] taskkill by window title...
taskkill /f /fi "WINDOWTITLE eq CN Backend*" >nul 2>&1
if errorlevel 1 (
    echo [INFO] No window titled CN Backend
) else (
    echo [OK] CN Backend window closed
)
taskkill /f /fi "WINDOWTITLE eq CN Frontend*" >nul 2>&1
if errorlevel 1 (
    echo [INFO] No window titled CN Frontend
) else (
    echo [OK] CN Frontend window closed
)
echo.

echo [2/3] free port 8014 ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-NetTCPConnection -LocalPort 8014 -ErrorAction SilentlyContinue | Where-Object { $_.State -match 'Listen' } | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
echo [OK] port 8014 done
echo.

echo [3/3] free port 5176 ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-NetTCPConnection -LocalPort 5176 -ErrorAction SilentlyContinue | Where-Object { $_.State -match 'Listen' } | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
echo [OK] port 5176 done
echo.

echo ============================================================
echo Done.
echo ============================================================
if not defined NOPAUSE pause
