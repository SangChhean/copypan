#!/bin/bash
# CN 站数据备份脚本
# 用法：bash backup_cn.sh
# 建议加入 crontab：0 2 * * * bash /opt/pansearch/code/back_cn/scripts/backup_cn.sh >> /opt/pansearch/logs/backup_cn.log 2>&1

set -e

BACKUP_DIR="/opt/pansearch/backups/cn"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"

echo "[$(date)] 开始 CN 站备份..."

# 1. cn_users.db（sqlite3 online backup，避免热拷贝损坏）
DB_SRC="/opt/pansearch/code/back_cn/cn_users.db"
DB_DST="$BACKUP_DIR/cn_users_${DATE}.db"
if [ -f "$DB_SRC" ]; then
    sqlite3 "$DB_SRC" ".backup '$DB_DST'"
    echo "[OK] cn_users.db → $DB_DST"
else
    echo "[SKIP] cn_users.db 不存在，跳过"
fi

# 2. cn_materials（rsync 增量备份）
MATERIALS_SRC="/opt/pansearch/data/cn_materials/"
MATERIALS_DST="$BACKUP_DIR/cn_materials/"
mkdir -p "$MATERIALS_DST"
rsync -av --delete "$MATERIALS_SRC" "$MATERIALS_DST"
echo "[OK] cn_materials → $MATERIALS_DST"

# 3. 清理 30 天前的 db 备份
find "$BACKUP_DIR" -name "cn_users_*.db" -mtime +30 -delete
echo "[OK] 已清理 30 天前的旧备份"

echo "[$(date)] CN 站备份完成"
