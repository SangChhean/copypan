#!/bin/bash
echo "=========================================="
echo "  🚀 Pansearch 自动化部署"
echo "=========================================="
echo ""
CODE_DIR="/opt/pansearch/code"
LOG_DIR="/opt/pansearch/logs"
BACKUP_DIR="/opt/pansearch/backups"
mkdir -p "$LOG_DIR"
echo "[1/7] 备份当前代码..."
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"
tar -czf "$BACKUP_DIR/code_backup_$DATE.tar.gz" "$CODE_DIR" 2>/dev/null
echo "✅ 备份完成"
echo "[2/7] 拉取最新代码..."
cd "$CODE_DIR"
git pull origin master
echo "✅ 代码更新完成"
echo "[3/7] 安装 Python 依赖..."
if [ -f "$CODE_DIR/back_mic/backend/requirements.txt" ]; then
    pip install -r "$CODE_DIR/back_mic/backend/requirements.txt" -q
    echo "✅ 依赖已更新"
fi
echo "[4/7] 构建前端..."
FRONT_DIR="$CODE_DIR/front_mic/frontend"
if [ -f "$FRONT_DIR/package.json" ]; then
    cd "$FRONT_DIR"
    npm ci --silent 2>/dev/null || npm install --silent
    npm run build
    cd "$CODE_DIR"
    echo "✅ 前端构建完成"
else
    echo "⚠️ 未找到 front_mic/frontend，跳过前端构建"
fi
echo "[5/7] 检查 Neo4j..."
if ! docker ps | grep -q "neo4j"; then
    echo "⚠️ Neo4j 未运行，正在启动..."
    docker start neo4j
    sleep 5
    echo "✅ Neo4j 已启动"
else
    echo "✅ Neo4j 已在运行"
fi
echo "[6/7] 重启后端服务..."
pkill uvicorn 2>/dev/null
sleep 2
cd "$CODE_DIR/back_mic/backend"
nohup uvicorn main:app --host 0.0.0.0 --port 8000 > "$LOG_DIR/backend.log" 2>&1 &
echo "✅ 后端已重启"
echo "[7/7] 重启 Nginx..."
systemctl reload nginx
echo "✅ Nginx 已重启"
echo ""
echo "=========================================="
echo "✅ 部署完成！"
echo "🌐 网站: https://aipansearch.org"
echo "📋 查看日志: tail -f $LOG_DIR/backend.log"
echo "📁 前端静态: $FRONT_DIR/dist（请确认 Nginx root 指向此目录）"
echo "=========================================="