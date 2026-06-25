#!/bin/bash
# 将 back_anshifenliang/data 软链到 front_anshifenliang（不重复存数据）
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
SRC="${DATA_SRC:-$(cd "$ROOT/../back_anshifenliang/data" && pwd)}"

if [ ! -d "$SRC" ]; then
  echo "Data source not found: $SRC" >&2
  exit 1
fi

link_file() {
  local name="$1"
  local dst="$ROOT/$name"
  local src="$SRC/$name"
  [ -f "$src" ] || { echo "skip missing: $name"; return; }
  if [ -e "$dst" ] && [ ! -L "$dst" ]; then rm -f "$dst"; fi
  if [ ! -e "$dst" ]; then ln -sf "$src" "$dst" && echo "linked $name"; fi
}

for f in traditional_to_simplified.js simplified_to_traditional.js \
  qu-bie-ci-exclusion-map.js hymns.js shi_ge.js shi_ge_fen_lei.js \
  zhu_jie_wen_da.js cha_kan_zheng_pian.js jing_jie_wen_da.js \
  xiao_bai_ke.js bible_verse.js jing_jie_zhu_shi.js \
  styles.css content_view.html viewer_host.html favicon.ico; do
  link_file "$f"
done

PRIVATE_DST="$ROOT/private"
PRIVATE_SRC="$SRC/private"
if [ -d "$PRIVATE_SRC" ]; then
  if [ -e "$PRIVATE_DST" ] && [ ! -L "$PRIVATE_DST" ]; then rm -rf "$PRIVATE_DST"; fi
  if [ ! -e "$PRIVATE_DST" ]; then ln -sf "$PRIVATE_SRC" "$PRIVATE_DST" && echo "linked private/"; fi
fi

echo "Done. Data linked from $SRC"
