@echo off
setlocal EnableExtensions
title Copypan FL Stop
if /i "%~1"=="nopause" set "NOPAUSE=1"

echo ============================================================
echo Copypan FL stop
echo ============================================================
echo.

echo [1/2] taskkill by window title...
taskkill /f /fi "WINDOWTITLE eq FL Backend*" >nul 2>&1
if errorlevel 1 (
    echo [INFO] No window titled FL Backend
) else (
    echo [OK] FL Backend window closed
)
taskkill /f /fi "WINDOWTITLE eq FL Frontend*" >nul 2>&1
if errorlevel 1 (
    echo [INFO] No window titled FL Frontend
) else (
    echo [OK] FL Frontend window closed
)
echo.

echo [2/3] free port 8020 ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-NetTCPConnection -LocalPort 8020 -ErrorAction SilentlyContinue | Where-Object { $_.State -match 'Listen' } | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
echo [OK] port 8020 done
echo.

echo [3/3] free port 5177 ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-NetTCPConnection -LocalPort 5177 -ErrorAction SilentlyContinue | Where-Object { $_.State -match 'Listen' } | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
echo [OK] port 5177 done
echo.

echo ============================================================
echo Done.
echo ============================================================
if not defined NOPAUSE pause
