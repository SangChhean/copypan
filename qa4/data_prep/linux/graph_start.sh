#!/usr/bin/env bash
# 交互输入密码后，用 docker compose 启动 qa4-neo4j。
# 密码仅存在于本进程环境变量 QA4_NEO4J_PASSWORD，结束时清除；不写文件、不打印。
# 注意：NEO4J_AUTH 仅对尚未初始化的数据卷生效；已 load 过的卷请使用当初设库密码。
set -euo pipefail
# shellcheck source=_common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

CONTAINER="qa4-neo4j"
COMPOSE_FILE="${QA4_INFRA_DIR}/docker-compose.neo4j.yml"
qa4_assert_container_name "$CONTAINER"
qa4_require_env_file_mode
qa4_require_mem_limit QA4_NEO4J_MEM_LIMIT
qa4_ensure_data_dirs
qa4_print_runtime_settings
qa4_refuse_foreign_container_name "$CONTAINER"
qa4_refuse_port_conflict 7476 "$CONTAINER"
qa4_refuse_port_conflict 7689 "$CONTAINER"

[[ -f "$COMPOSE_FILE" ]] || qa4_die "找不到 compose: ${COMPOSE_FILE}"

if ! docker volume ls --format '{{.Name}}' | grep -qx 'qa4_neo4j_data'; then
  qa4_die "卷 qa4_neo4j_data 不存在。请先运行 graph_load.sh"
fi
if ! docker volume ls --format '{{.Name}}' | grep -qx 'qa4_neo4j_logs'; then
  docker volume create qa4_neo4j_logs >/dev/null
fi

echo "提示：已初始化的 qa4-neo4j 请输入与 load/首次启动时相同的密码（NEO4J_AUTH 对已有数据卷不重置密码）。"
echo "请输入 QA4_NEO4J_PASSWORD（输入不可见）:"
read -rs QA4_NEO4J_PASSWORD
echo
[[ -n "${QA4_NEO4J_PASSWORD}" ]] || qa4_die "密码为空，已中止。"
export QA4_NEO4J_PASSWORD

cleanup() {
  unset QA4_NEO4J_PASSWORD || true
}
trap cleanup EXIT

echo "启动 compose 服务 qa4-neo4j ..."
docker compose -f "$COMPOSE_FILE" --project-directory "$QA4_INFRA_DIR" up -d qa4-neo4j

echo "等待容器日志出现 Started ..."
deadline=$((SECONDS + 180))
ok=0
while (( SECONDS < deadline )); do
  if docker logs "$CONTAINER" 2>&1 | grep -q 'Started'; then
    ok=1
    break
  fi
  sleep 2
done

if [[ "$ok" -ne 1 ]]; then
  qa4_die "超时：未在日志中看到 Started。请自行检查: docker logs ${CONTAINER}"
fi

echo "qa4-neo4j 已启动（日志含 Started）。Browser http://127.0.0.1:7476  Bolt bolt://127.0.0.1:7689"
