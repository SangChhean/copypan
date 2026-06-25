#!/bin/bash
# 搬瓦工一键部署 — 后端 + Bot + Nginx + SSL
#
# 用法：
#   bash back_anshifenliang/deploy.sh
#
# 环境变量（均可选）：
#   CODE_DIR          代码目录（默认 /opt/pansearch/code）
#   DOMAIN            域名（默认 chat.educationbylevel.org）
#   SSL_EMAIL         Let's Encrypt 邮箱（建议设置）
#   APPLY_SSL         是否申请/检查 SSL（默认 1）
#   SKIP_NGINX        跳过 Nginx（默认 0）
#   SKIP_BACKEND      跳过后端重启（默认 0）
#   SKIP_BOT          跳过 Bot（默认 0）
#   TELEGRAM_BOT_TOKEN  Telegram Bot Token
set -e

CODE_DIR="${CODE_DIR:-/opt/pansearch/code}"
LOG_DIR="${LOG_DIR:-/opt/pansearch/logs}"
DATA_DIR="${DATA_DIR:-$CODE_DIR/back_anshifenliang/data}"
PORT="${PORT:-8020}"
DOMAIN="${DOMAIN:-chat.educationbylevel.org}"
NGINX_CONF="$CODE_DIR/front_anshifenliang/nginx/anshifenliang.conf"
APPLY_SSL="${APPLY_SSL:-1}"
SKIP_NGINX="${SKIP_NGINX:-0}"
SKIP_BACKEND="${SKIP_BACKEND:-0}"
SKIP_BOT="${SKIP_BOT:-0}"

deploy_nginx() {
  if [ "$SKIP_NGINX" = "1" ]; then
    echo "⚠️ SKIP_NGINX=1，跳过 Nginx"
    return 0
  fi
  if ! command -v nginx &>/dev/null; then
    echo "⚠️ 未安装 nginx，跳过 Nginx 配置"
    return 0
  fi
  if [ ! -f "$NGINX_CONF" ]; then
    echo "⚠️ 找不到 $NGINX_CONF，跳过 Nginx"
    return 0
  fi

  echo "[5/6] 部署 Nginx..."
  mkdir -p /var/www/certbot
  cp "$NGINX_CONF" /etc/nginx/sites-available/anshifenliang.conf
  ln -sf /etc/nginx/sites-available/anshifenliang.conf /etc/nginx/sites-enabled/anshifenliang.conf
  nginx -t
  systemctl reload nginx
  echo "✅ Nginx 已重载 — http://$DOMAIN"
}

deploy_ssl() {
  if [ "$APPLY_SSL" != "1" ]; then
    echo "⚠️ APPLY_SSL!=1，跳过 SSL"
    return 0
  fi
  if ! command -v nginx &>/dev/null; then
    echo "⚠️ 未安装 nginx，跳过 SSL"
    return 0
  fi

  echo "[6/6] SSL 证书..."
  CERT_PATH="/etc/letsencrypt/live/$DOMAIN/fullchain.pem"

  if [ -f "$CERT_PATH" ]; then
    echo "✅ 证书已存在: $CERT_PATH"
    if command -v certbot &>/dev/null; then
      certbot renew --dry-run 2>/dev/null && echo "✅ 续期检查通过" || echo "⚠️ 续期预检有问题，请稍后检查"
    fi
    return 0
  fi

  if ! command -v certbot &>/dev/null; then
    echo "  安装 certbot..."
    if command -v apt-get &>/dev/null; then
      apt-get update -qq
      apt-get install -y certbot python3-certbot-nginx
    elif command -v yum &>/dev/null; then
      yum install -y certbot python3-certbot-nginx
    else
      echo "⚠️ 无法安装 certbot，跳过 SSL。请手动: bash setup-ssl.sh"
      return 0
    fi
  fi

  PUBLIC_IP=$(curl -s --max-time 5 ifconfig.me 2>/dev/null || curl -s --max-time 5 icanhazip.com 2>/dev/null || true)
  RESOLVED=$(dig +short "$DOMAIN" 2>/dev/null | tail -1 || true)
  echo "  公网 IP: ${PUBLIC_IP:-未知}  |  $DOMAIN → ${RESOLVED:-未解析}"
  if [ -n "$PUBLIC_IP" ] && [ -n "$RESOLVED" ] && [ "$PUBLIC_IP" != "$RESOLVED" ]; then
    echo "  ⚠️ DNS 可能未指向本机，SSL 申请可能失败"
  fi

  CERTBOT_ARGS=(certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos)
  if [ -n "${SSL_EMAIL:-}" ]; then
    CERTBOT_ARGS+=(--email "$SSL_EMAIL")
  else
    CERTBOT_ARGS+=(--register-unsafely-without-email)
  fi

  if "${CERTBOT_ARGS[@]}"; then
    echo "✅ SSL 证书已申请 — https://$DOMAIN"
    if ! crontab -l 2>/dev/null | grep -q certbot; then
      (crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet --post-hook 'systemctl reload nginx'") | crontab -
      echo "✅ 已添加证书自动续期 cron"
    fi
    nginx -t && systemctl reload nginx
  else
    echo "⚠️ SSL 申请失败（DNS/防火墙未就绪？）。站点仍可通过 HTTP 访问。"
    echo "   修复后重跑: SSL_EMAIL=you@mail.com bash $CODE_DIR/back_anshifenliang/deploy.sh"
    return 0
  fi
}

echo "=========================================="
echo "  按时分粮 一键部署"
echo "=========================================="

if [ "$SKIP_BACKEND" != "1" ]; then
  echo "[1/6] 安装 Node 依赖..."
  cd "$CODE_DIR/back_anshifenliang"
  npm ci --silent 2>/dev/null || npm install --silent

  echo "[1b/6] 构建数据索引..."
  export DATA_DIR
  npm run build || echo "⚠️ build 未完成（若无 foo_jie 源目录，请确保 data/private/foo_jie_single 已随代码部署）"

  echo "[2/6] 重启 back_anshifenliang..."
  pkill -f "node.*back_anshifenliang/server.js" 2>/dev/null || true
  sleep 1
  export DATA_DIR PORT
  nohup node server.js > "$LOG_DIR/anshifenliang.log" 2>&1 &
  echo "✅ back_anshifenliang :$PORT"
else
  echo "[1-2/6] SKIP_BACKEND=1，跳过后端"
fi

echo "[3/6] 链接 front 数据..."
if [ -f "$CODE_DIR/front_anshifenliang/setup-data.sh" ]; then
  bash "$CODE_DIR/front_anshifenliang/setup-data.sh"
  echo "✅ front 数据已链接"
fi

if [ "$SKIP_BOT" != "1" ]; then
  echo "[4/6] 安装 Bot 依赖..."
  pip install -q -r "$CODE_DIR/back_anshifenliang/telegram_bot/requirements.txt"

  echo "[4b/6] 重启 Telegram Bot..."
  pkill -f "back_anshifenliang/telegram_bot/bot.py" 2>/dev/null || true
  sleep 1
  export ANSHIFENLIANG_API="http://127.0.0.1:$PORT"
  BOT_TOKEN_EFFECTIVE="${TELEGRAM_BOT_TOKEN:-${BOT_TOKEN:-}}"
  if [ -n "$BOT_TOKEN_EFFECTIVE" ]; then
    export TELEGRAM_BOT_TOKEN="$BOT_TOKEN_EFFECTIVE"
    export BOT_TOKEN="$BOT_TOKEN_EFFECTIVE"
    nohup python3 "$CODE_DIR/back_anshifenliang/telegram_bot/bot.py" \
      > "$LOG_DIR/anshifenliang_bot.log" 2>&1 &
    echo "✅ Telegram Bot 已启动"
  else
    echo "⚠️ 未设置 TELEGRAM_BOT_TOKEN，跳过 Bot"
  fi
else
  echo "[4/6] SKIP_BOT=1，跳过 Bot"
fi

deploy_nginx
deploy_ssl

echo ""
echo "=========================================="
echo "✅ 部署完成"
echo "🌐 https://$DOMAIN  (SSL 成功时)"
echo "🌐 http://$DOMAIN   (SSL 未申请时)"
echo "📋 后端日志: tail -f $LOG_DIR/anshifenliang.log"
echo "📋 健康检查: curl http://127.0.0.1:$PORT/api/health"
echo "=========================================="
