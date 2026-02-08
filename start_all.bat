@echo off
chcp 65001 >nul
title Copypan 一键启动

REM Nginx 部署目录（若你的 Nginx 不在 C:\nginx-1.24.0 请改此处）
set "NGINX_HTML=C:\nginx-1.24.0\html"
set "NGINX_DIR=C:\nginx-1.24.0"

echo ============================================================
echo              Copypan 网站一键启动脚本
echo ============================================================
echo.

REM 检查Docker Desktop是否运行
echo [1/7] 检查Docker状态...
docker ps >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Docker未运行！请先启动Docker Desktop
    echo.
    pause
    exit /b 1
)
echo ✓ Docker正在运行
echo.

REM 启动Elasticsearch容器
echo [2/7] 启动Elasticsearch...
docker start elasticsearch >nul 2>&1
if %errorlevel% neq 0 (
    echo ⚠ Elasticsearch容器不存在，正在创建...
    docker run -d --name elasticsearch ^
      -p 9200:9200 ^
      -p 9300:9300 ^
      -e "discovery.type=single-node" ^
      -e "ES_JAVA_OPTS=-Xms2g -Xmx2g" ^
      -v E:\copypan\es_data:/usr/share/elasticsearch/data ^
      elasticsearch:7.17.9
    echo ✓ Elasticsearch容器已创建
) else (
    echo ✓ Elasticsearch已启动
)

echo   等待Elasticsearch就绪...
timeout /t 15 /nobreak >nul
echo.

REM 启动Kibana容器
echo [3/7] 启动Kibana管理界面...
docker start kibana >nul 2>&1
if %errorlevel% neq 0 (
    echo ⚠ Kibana容器不存在，正在创建...
    docker run -d --name kibana ^
      -p 5601:5601 ^
      -e "ELASTICSEARCH_HOSTS=http://host.docker.internal:9200" ^
      kibana:7.17.9
    echo ✓ Kibana容器已创建
    echo   提示：Kibana首次启动需要1-2分钟
) else (
    echo ✓ Kibana已启动
)
echo.

REM 启动 Redis（AI 缓存与统计）
echo [4/7] 启动 Redis...
docker start redis >nul 2>&1
if %errorlevel% neq 0 (
    echo ⚠ 未检测到 Redis 容器，AI 缓存与统计将不可用
    echo   可选：docker run -d --name redis -p 6379:6379 redis:alpine
) else (
    echo ✓ Redis 已启动
)
echo.

REM 启动后端FastAPI
echo [5/7] 启动后端服务...
start "Copypan Backend" cmd /k "cd /d E:\copypan\back_mic\backend && echo ============================================================ && echo                      后端服务 (端口8000) && echo ============================================================ && echo. && uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
echo ✓ 后端服务已启动（新窗口）
timeout /t 3 /nobreak >nul
echo.

REM 构建前端（无 dist 或 dist 无 index.html 时执行构建）
echo [6/7] 构建并部署前端...
cd /d E:\copypan\front_mic\frontend
if not exist "dist\index.html" (
    echo   正在执行 npm run build，请稍候...
    call npm run build
    if %errorlevel% neq 0 (
        echo ❌ 前端构建失败，请检查 Node 与 npm 是否已安装
        pause
        exit /b 1
    )
    echo ✓ 前端构建完成
) else (
    echo ✓ 前端已构建（dist 已存在）
)
if exist "dist\index.html" (
    if not exist "%NGINX_HTML%" mkdir "%NGINX_HTML%"
    xcopy /E /Y /Q dist\* "%NGINX_HTML%\" >nul 2>&1
    echo ✓ 已部署到 %NGINX_HTML%
    echo   请确认 Nginx 配置中 root 指向此目录，否则会白屏
)
echo.

REM 启动Nginx
echo [7/7] 启动Nginx...
cd /d "%NGINX_DIR%"
start nginx.exe
echo ✓ Nginx已启动
timeout /t 2 /nobreak >nul
echo.

REM 打开浏览器
echo 打开网站...
timeout /t 3 /nobreak >nul
start http://localhost
echo ✓ 浏览器已打开
echo.

set "STOPBAT=stop_all.bat"
echo ============================================================
echo              启动完成！服务运行状态：
echo ============================================================
echo.
echo   * Elasticsearch:    http://localhost:9200
echo   * Kibana:           http://localhost:5601
echo   * Redis:            localhost:6379 (AI 缓存与统计)
echo   * 后端API:          http://localhost:8000
echo   * 前端网站:         http://localhost
echo.
echo   [登录] 用户名 admin  密码 Pass2Pansearch
echo.
echo   [Kibana] 首次启动需1-2分钟，进入后选 Explore on my own
echo.
echo   [若白屏] 确认 Nginx 的 root 为 %NGINX_HTML%，参考 nginx.conf.example
echo.
echo ============================================================
echo   关闭此窗口不会停止服务；停止请运行 %STOPBAT%
echo ============================================================
echo.
pause