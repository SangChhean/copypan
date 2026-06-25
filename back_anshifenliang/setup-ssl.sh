#!/bin/bash
# 仅补跑 SSL（后端/Bot 不重启）
# 等价于: APPLY_SSL=1 SKIP_BACKEND=1 SKIP_BOT=1 bash deploy.sh
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
export APPLY_SSL=1
export SKIP_BACKEND=1
export SKIP_BOT=1
exec bash "$SCRIPT_DIR/deploy.sh"
