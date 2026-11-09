#!/usr/bin/env bash
# 构建并启动 qa4-es（交互输入密码；不打印、不落盘）。
# 用法：
#   bash ./es_start.sh
#   QA4_DATA_ROOT=/opt/qa4_data bash ./es_start.sh
set -euo pipefail
# shellcheck source=_common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

CONTAINER="qa4-es"
COMPOSE_FILE="${QA4_INFRA_DIR}/docker-compose.es.yml"
qa4_assert_container_name "$CONTAINER"
qa4_require_env_file_mode
qa4_require_mem_limit QA4_ES_MEM_LIMIT
qa4_ensure_data_dirs
qa4_print_runtime_settings
qa4_refuse_foreign_container_name "$CONTAINER"
qa4_refuse_port_conflict 9202 "$CONTAINER"

[[ -f "$COMPOSE_FILE" ]] || qa4_die "找不到 compose: ${COMPOSE_FILE}"

echo "请输入 QA4_ES_PASSWORD（输入不可见）:"
read -rs QA4_ES_PASSWORD
echo
[[ -n "${QA4_ES_PASSWORD}" ]] || qa4_die "密码为空，已中止。"
export QA4_ES_PASSWORD
export QA4_ES_DATA_DIR

cleanup() {
  unset QA4_ES_PASSWORD || true
}
trap cleanup EXIT

echo "docker compose up -d --build qa4-es ..."
docker compose -f "$COMPOSE_FILE" --project-directory "$QA4_INFRA_DIR" up -d --build qa4-es

echo "等待 _cluster/health 变为 green 或 yellow（最多 5 分钟）..."
deadline=$((SECONDS + 300))
ok=0
while (( SECONDS < deadline )); do
  # 密码仅在容器内通过 curl -K 配置传入，不出现在宿主机 docker exec 参数中
  # shellcheck disable=SC2016
  if status="$(docker exec "$CONTAINER" bash -c \
      'printf "user = \"elastic:%s\"\n" "$ELASTIC_PASSWORD" | curl -s -K - http://localhost:9200/_cluster/health' \
      | sed -n 's/.*"status"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1)"; then
    if [[ "$status" == "green" || "$status" == "yellow" ]]; then
      echo "健康检查通过: status=${status}"
      ok=1
      break
    fi
  fi
  sleep 3
done

if [[ "$ok" -ne 1 ]]; then
  qa4_die "超时：集群未达到 green/yellow。请检查: docker logs ${CONTAINER}"
fi

echo "qa4-es 已就绪。HTTP http://127.0.0.1:9202"
