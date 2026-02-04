@echo off
chcp 65001 >nul
title Copypan 一键启动

echo ============================================================
echo              Copypan 网站一键启动脚本
echo ============================================================
echo.

REM 检查Docker Desktop是否运行
echo [1/6] 检查Docker状态...
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
echo [2/6] 启动Elasticsearch...
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
echo [3/6] 启动Kibana管理界面...
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

REM 启动后端FastAPI
echo [4/6] 启动后端服务...
start "Copypan Backend" cmd /k "cd /d E:\copypan\back_mic\backend && echo ============================================================ && echo                      后端服务 (端口8000) && echo ============================================================ && echo. && uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
echo ✓ 后端服务已启动（新窗口）
timeout /t 3 /nobreak >nul
echo.

REM 启动Nginx
echo [5/6] 启动Nginx...
cd /d C:\nginx-1.24.0
start nginx.exe
echo ✓ Nginx已启动
timeout /t 2 /nobreak >nul
echo.

REM 打开浏览器
echo [6/6] 打开网站...
timeout /t 3 /nobreak >nul
start http://localhost
echo ✓ 浏览器已打开
echo.

echo ============================================================
echo              启动完成！服务运行状态：
echo ============================================================
echo.
echo  🔹 Elasticsearch:    http://localhost:9200
echo  🔹 Kibana管理界面:   http://localhost:5601
echo  🔹 后端API:          http://localhost:8000
echo  🔹 前端网站:         http://localhost
echo.
echo  📝 网站登录：
echo     用户名: admin
echo     密码:   Pass2Pansearch
echo.
echo  💡 Kibana使用提示：
echo     - 首次启动需要1-2分钟
echo     - 进入后选择 "Explore on my own"
echo     - 使用 Dev Tools 执行ES查询
echo     - 使用 Discover 浏览数据
echo.
echo ============================================================
echo  提示：
echo  - 关闭此窗口不会停止服务
echo  - 使用 stop_all.bat 停止所有服务
echo  - 后端日志在单独的窗口中显示
echo ============================================================
echo.
pause