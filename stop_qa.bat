@echo off
setlocal EnableExtensions
title Copypan QA Stop
if /i "%~1"=="nopause" set "NOPAUSE=1"

echo ============================================================
echo Copypan QA stop
echo ============================================================
echo.

echo [1/3] taskkill by window title...
taskkill /f /fi "WINDOWTITLE eq QA Backend*" >nul 2>&1
if errorlevel 1 (
    echo [INFO] No window titled QA Backend
) else (
    echo [OK] QA Backend window closed
)
taskkill /f /fi "WINDOWTITLE eq QA Frontend*" >nul 2>&1
if errorlevel 1 (
    echo [INFO] No window titled QA Frontend
) else (
    echo [OK] QA Frontend window closed
)
echo.

echo [2/3] free port 8001 ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-NetTCPConnection -LocalPort 8001 -ErrorAction SilentlyContinue | Where-Object { $_.State -match 'Listen' } | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
echo [OK] port 8001 done
echo.

echo [3/3] free port 5174 ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-NetTCPConnection -LocalPort 5174 -ErrorAction SilentlyContinue | Where-Object { $_.State -match 'Listen' } | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
echo [OK] port 5174 done
echo.

echo ============================================================
echo Done. If anything remains, check python.exe / node.exe in Task Manager.
echo ============================================================
if not defined NOPAUSE pause
