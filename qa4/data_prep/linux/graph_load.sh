#!/usr/bin/env bash
# 将 neo4j.dump 载入命名卷 qa4_neo4j_data（一次性容器，不启动正式服务）。
# 用法：
#   ./graph_load.sh
#   ./graph_load.sh /path/to/dir_containing_neo4j.dump
#   ./graph_load.sh /path/to/dir --force
# 不需要密码。--force 时会移除已有 qa4-neo4j 容器与 qa4_neo4j_data 卷后重建。
set -euo pipefail
# shellcheck source=_common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

EXPECTED_SHA="B5B0C10C657E0FF03309A6D21603DC11B3152D66037F499EAD266948721089C4"
IMAGE="neo4j:5.26.28"
VOLUME="qa4_neo4j_data"
CONTAINER="qa4-neo4j"
DB_NAME="neo4j"

DUMP_DIR="${QA4_DATA_ROOT}/graph"
FORCE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --force) FORCE=1; shift ;;
    -*) qa4_die "未知参数: $1" ;;
    *) DUMP_DIR="$1"; shift ;;
  esac
done

qa4_assert_container_name "$CONTAINER"
qa4_require_env_file_mode
qa4_ensure_data_dirs

DUMP_PATH="${DUMP_DIR}/neo4j.dump"
[[ -f "$DUMP_PATH" ]] || qa4_die "找不到 dump: ${DUMP_PATH}"

echo "核对 dump SHA256 ..."
actual_sha="$(sha256sum "$DUMP_PATH" | awk '{print toupper($1)}')"
if [[ "$actual_sha" != "$EXPECTED_SHA" ]]; then
  echo "SHA256 不一致，已中止。"
  echo "  期望: ${EXPECTED_SHA}"
  echo "  实际: ${actual_sha}"
  exit 1
fi
echo "SHA256 一致。"

volume_exists() {
  docker volume ls --format '{{.Name}}' | grep -qx "$1"
}

volume_nonempty() {
  volume_exists "$1" || return 1
  local out
  out="$(docker run --rm --volume "${1}:/data:ro" "$IMAGE" ls -A /data 2>/dev/null || true)"
  [[ -n "${out// }" ]]
}

container_exists=0
qa4_container_exists "$CONTAINER" && container_exists=1
vol_exists=0
volume_exists "$VOLUME" && vol_exists=1
vol_nonempty=0
if [[ "$vol_exists" -eq 1 ]] && volume_nonempty "$VOLUME"; then
  vol_nonempty=1
fi

if [[ "$FORCE" -ne 1 ]]; then
  if [[ "$container_exists" -eq 1 ]]; then
    qa4_die "已存在容器 '${CONTAINER}'。未指定 --force，拒绝继续（本脚本不会自动删除）。"
  fi
  if [[ "$vol_nonempty" -eq 1 ]]; then
    qa4_die "卷 '${VOLUME}' 已存在且非空。未指定 --force，拒绝继续（本脚本不会自动删除）。"
  fi
fi

if [[ "$FORCE" -eq 1 ]]; then
  if [[ "$container_exists" -eq 1 ]]; then
    echo "--force: 移除容器 ${CONTAINER} ..."
    docker rm -f "$CONTAINER" >/dev/null
  fi
  if volume_exists "$VOLUME"; then
    echo "--force: 删除卷 ${VOLUME} ..."
    docker volume rm "$VOLUME" >/dev/null
  fi
fi

if ! volume_exists "$VOLUME"; then
  echo "创建卷 ${VOLUME} ..."
  docker volume create "$VOLUME" >/dev/null
fi

echo "一次性容器执行 neo4j-admin database load (${DB_NAME}) ..."
docker run --rm \
  --volume "${VOLUME}:/data" \
  --volume "${DUMP_DIR}:/dump:ro" \
  "$IMAGE" \
  neo4j-admin database load "$DB_NAME" --from-path=/dump --overwrite-destination=true

# 校正卷内属主为 neo4j uid（绕过镜像 entrypoint）
docker run --rm --user root --entrypoint chown \
  --volume "${VOLUME}:/data" "$IMAGE" -R 7474:7474 /data 2>/dev/null || true

echo "load 完成。请再运行 graph_start.sh 启动正式容器 qa4-neo4j。"
