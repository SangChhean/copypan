@echo off
setlocal
title Copypan Start All

cd /d "%~dp0"
set "PROJECT_DIR=%CD%"
set "BACKEND_DIR=%PROJECT_DIR%\back_mic\backend"
set "FRONTEND_DIR=%PROJECT_DIR%\front_mic\frontend"
set "NGINX_DIR=A:\nginx-1.24.0"
set "NGINX_HTML=%NGINX_DIR%\html"

echo ============================================================
echo Copypan Start Script
echo ============================================================
echo.

where docker >nul 2>&1
if errorlevel 1 (
    echo [ERROR] docker command not found. Please install Docker Desktop.
    pause
    exit /b 1
)

echo [1/7] Checking Docker...
docker ps >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker is not running. Please start Docker Desktop first.
    pause
    exit /b 1
)
echo [OK] Docker is running.
echo.

echo [2/7] Starting Elasticsearch 8...
docker start elasticsearch8 >nul 2>&1
if errorlevel 1 (
    echo [WARN] elasticsearch8 container not found. Creating...
    docker run -d --name elasticsearch8 ^
      -p 9200:9200 ^
      -p 9300:9300 ^
      -e "discovery.type=single-node" ^
      -e "xpack.security.enabled=true" ^
      -e "ELASTIC_PASSWORD=qwSD4AF2Dcv" ^
      -e "ES_JAVA_OPTS=-Xms2g -Xmx2g" ^
      -v "%PROJECT_DIR:\=/%/es_data:/usr/share/elasticsearch/data" ^
      elasticsearch:8.19.0 >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Failed to create elasticsearch8 container.
        pause
        exit /b 1
    )
)
echo [OK] Elasticsearch8 ready.
echo Waiting 15 seconds for ES warmup...
timeout /t 15 /nobreak >nul
echo.

echo [3/7] Starting Redis...
docker start redis >nul 2>&1
if errorlevel 1 (
    echo [WARN] redis container not found. AI cache/stats may be unavailable.
) else (
    echo [OK] Redis started.
)
echo.

echo [4/7] Starting Neo4j...
docker start neo4j >nul 2>&1
if errorlevel 1 (
    echo [WARN] neo4j container not found. KG graph features may be unavailable.
) else (
    echo [OK] Neo4j started.
)
echo.

where uvicorn >nul 2>&1
if errorlevel 1 (
    echo [ERROR] uvicorn command not found. Activate your Python environment first.
    pause
    exit /b 1
)

echo [5/7] Starting backend (new window)...
start "Copypan Backend" cmd /k "cd /d %BACKEND_DIR% && echo Backend on :8000 && uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
echo [OK] Backend window created.
timeout /t 3 /nobreak >nul
echo.

where npm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] npm command not found. Please install Node.js.
    pause
    exit /b 1
)

echo [6/7] Building and deploying frontend...
cd /d "%FRONTEND_DIR%"
if not exist "dist\index.html" (
    echo Running npm run build...
    call npm run build
    if errorlevel 1 (
        echo [ERROR] Frontend build failed.
        pause
        exit /b 1
    )
    echo [OK] Frontend build completed.
) else (
    echo [OK] Frontend already built.
)
if exist "dist\index.html" (
    if not exist "%NGINX_HTML%" mkdir "%NGINX_HTML%"
    xcopy /E /Y /Q dist\* "%NGINX_HTML%\" >nul 2>&1
    echo [OK] Frontend deployed to %NGINX_HTML%
)
echo.

echo [7/7] Starting Nginx...
if not exist "%NGINX_DIR%\nginx.exe" (
    echo [ERROR] nginx.exe not found under %NGINX_DIR%
    echo Please edit NGINX_DIR in this script.
    pause
    exit /b 1
)
set "NGINX_CONF_SRC=%PROJECT_DIR%\nginx.windows.conf"
if exist "%NGINX_CONF_SRC%" (
    set "NGINX_HTML_FWD=%NGINX_HTML:\=/%"
    set "NGINX_ROOT_PATH=%NGINX_HTML_FWD%"
    powershell -NoProfile -Command "$c = Get-Content -Raw '%NGINX_CONF_SRC%'; $c = $c -replace '__NGINX_HTML__', $env:NGINX_ROOT_PATH; [IO.File]::WriteAllText('%NGINX_DIR%\conf\nginx.conf', $c)"
    echo [OK] Nginx config deployed to %NGINX_DIR%\conf\nginx.conf
) else (
    echo [WARN] nginx.windows.conf not found. Using existing nginx.conf.
)
cd /d "%NGINX_DIR%"
nginx.exe -t
if errorlevel 1 (
    echo [ERROR] nginx.conf test failed. Check %NGINX_DIR%\conf\nginx.conf
    pause
    exit /b 1
)
taskkill /f /im nginx.exe >nul 2>&1
start "" nginx.exe
echo [OK] Nginx started.
timeout /t 2 /nobreak >nul
echo.

echo Opening website...
start http://localhost
echo.

echo ============================================================
echo Startup complete.
echo - Elasticsearch8: http://localhost:9200
echo - Neo4j:          http://localhost:7474  ^|  bolt://localhost:7687
echo - Redis:          localhost:6379
echo - Backend API:    http://localhost:8000
echo - Frontend:       http://localhost
echo ============================================================
echo To stop services, run stop_all.bat
echo.
pause