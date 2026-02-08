#!/bin/bash

echo "=========================================="
echo "  🚀 Pansearch 自动化部署"
echo "=========================================="
echo ""

CODE_DIR="/opt/pansearch/code"
LOG_DIR="/opt/pansearch/logs"
BACKUP_DIR="/opt/pansearch/backups"

# 确保日志目录存在（避免 nohup 重定向失败）
mkdir -p "$LOG_DIR"

# 1. 备份当前代码
echo "[1/6] 备份当前代码..."
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"
tar -czf "$BACKUP_DIR/code_backup_$DATE.tar.gz" "$CODE_DIR" 2>/dev/null
echo "✅ 备份完成"

# 2. 拉取最新代码
echo "[2/6] 拉取最新代码..."
cd "$CODE_DIR"
git pull origin master
echo "✅ 代码更新完成"

# 3. 安装 Python 依赖
echo "[3/6] 安装 Python 依赖..."
if [ -f "$CODE_DIR/back_mic/backend/requirements.txt" ]; then
    pip install -r "$CODE_DIR/back_mic/backend/requirements.txt" -q
    echo "✅ 依赖已更新"
fi

# 4. 构建前端（dist 未提交到 git，必须在服务器上构建）
echo "[4/6] 构建前端..."
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

# 5. 重启后端
echo "[5/6] 重启后端服务..."
pkill uvicorn 2>/dev/null
sleep 2
cd "$CODE_DIR/back_mic/backend"
nohup uvicorn main:app --host 0.0.0.0 --port 8000 > "$LOG_DIR/backend.log" 2>&1 &
echo "✅ 后端已重启"

# 6. 重启 Nginx
echo "[6/6] 重启 Nginx..."
systemctl reload nginx
echo "✅ Nginx 已重启"

echo ""
echo "=========================================="
echo "✅ 部署完成！"
echo "🌐 网站: https://aipansearch.org"
echo "📋 查看日志: tail -f $LOG_DIR/backend.log"
echo "📁 前端静态: $FRONT_DIR/dist（请确认 Nginx root 指向此目录）"
echo "=========================================="
