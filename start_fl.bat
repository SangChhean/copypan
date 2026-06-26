@echo off
setlocal EnableExtensions
title Copypan FL Start
if /i "%~1"=="nopause" set "NOPAUSE=1"

cd /d "%~dp0"
set "PROJECT_DIR=%CD%"
set "BACK_FL=%PROJECT_DIR%\back_anshifenliang"
set "FRONT_FL=%PROJECT_DIR%\front_anshifenliang"
set "FL_API_PORT=8020"
set "FL_WEB_PORT=5177"

echo ============================================================
echo Copypan FL start - back_anshifenliang + front_anshifenliang
echo ============================================================
echo.

where node >nul 2>&1
if errorlevel 1 (
    echo [ERROR] node not in PATH
    if not defined NOPAUSE pause
    exit /b 1
)

where npm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] npm not in PATH
    if not defined NOPAUSE pause
    exit /b 1
)

if not exist "%BACK_FL%\server.js" (
    echo [ERROR] Missing %BACK_FL%\server.js
    if not defined NOPAUSE pause
    exit /b 1
)

if not exist "%BACK_FL%\data\scripts.js" (
    echo [ERROR] Missing %BACK_FL%\data\scripts.js
    echo         Copy back_anshifenliang\data\ from server or colleague first.
    if not defined NOPAUSE pause
    exit /b 1
)

if not exist "%FRONT_FL%\index.html" (
    echo [ERROR] Missing %FRONT_FL%\index.html
    if not defined NOPAUSE pause
    exit /b 1
)

if not exist "%FRONT_FL%\private" (
    echo [data] Linking front data from back_anshifenliang\data ...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%FRONT_FL%\setup-data.ps1"
    if errorlevel 1 (
        echo [WARN] setup-data.ps1 failed; continue if data files already exist in front\
    ) else (
        echo [OK] front data linked
    )
    echo.
)

if not exist "%BACK_FL%\node_modules\express\package.json" (
    echo Installing back_anshifenliang dependencies...
    start "FL Backend Install" cmd /k "cd /d %BACK_FL% && npm install"
    echo [INFO] Please wait for install window to finish, then rerun start_fl.bat.
    if not defined NOPAUSE pause
    exit /b 1
)

echo [1/2] Starting back_anshifenliang in new window :%FL_API_PORT% ...
echo       First start loads data; may take 1-2 minutes.
start "FL Backend" cmd /k "cd /d %BACK_FL% && set PORT=%FL_API_PORT% && echo FL Backend http://127.0.0.1:%FL_API_PORT%/api/health && node server.js"
echo [OK] Backend window started
ping 127.0.0.1 -n 3 >nul
echo.

echo [2/2] Starting front_anshifenliang in new window :%FL_WEB_PORT% ...
start "FL Frontend" cmd /k "cd /d %FRONT_FL% && echo FL Frontend http://127.0.0.1:%FL_WEB_PORT% && npx --yes serve -l %FL_WEB_PORT%"
echo [OK] Frontend window started
echo.

echo ============================================================
echo Ready.
echo - API:  http://127.0.0.1:%FL_API_PORT%/api/health
echo - Web:  http://127.0.0.1:%FL_WEB_PORT%
echo.
echo Wait until backend shows "listening on :%FL_API_PORT%" before searching.
echo Local API is auto-used via front_anshifenliang\api_config.js
echo ============================================================
echo Stop: run stop_fl.bat
echo.
if not defined NOPAUSE pause
