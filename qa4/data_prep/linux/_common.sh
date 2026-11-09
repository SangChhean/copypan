# shellcheck shell=bash
# 供 qa4/data_prep/linux/*.sh source；不直接执行。
# 统一：set -euo pipefail、只允许 qa4* 容器名、.env 必须 600、数据目录属主。

set -euo pipefail

QA4_LINUX_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QA4_DATA_PREP_DIR="$(cd "${QA4_LINUX_DIR}/.." && pwd)"
QA4_ROOT="$(cd "${QA4_DATA_PREP_DIR}/.." && pwd)"
QA4_INFRA_DIR="$(cd "${QA4_ROOT}/infra" && pwd)"

qa4_die() {
  echo "ERROR: $*" >&2
  exit 1
}

# 安全读取 .env：不 source/eval；仅 ^QA4_[A-Z0-9_]+= ；已在环境中的键不覆盖；PASSWORD 键忽略。
qa4_load_dotenv_file() {
  local f="$1"
  [[ -f "$f" ]] || return 0
  local line key val
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ -z "${line//[[:space:]]/}" ]] && continue
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    [[ "$line" =~ ^QA4_[A-Z0-9_]+= ]] || continue
    key="${line%%=*}"
    val="${line#*=}"
    if [[ "$val" =~ ^\".*\"$ ]]; then
      val="${val:1:${#val}-2}"
    elif [[ "$val" =~ ^\'.*\'$ ]]; then
      val="${val:1:${#val}-2}"
    fi
    if [[ "$key" == *PASSWORD* ]]; then
      if [[ -n "$val" ]]; then
        echo "WARN: 密码不从 .env 读取，请清空 ${key}（文件 ${f}）" >&2
      fi
      continue
    fi
    # 已 export / 已在环境中的优先
    if printenv "$key" >/dev/null 2>&1; then
      continue
    fi
    export "${key}=${val}"
  done <"$f"
}

qa4_load_dotenv_files() {
  qa4_load_dotenv_file "${QA4_ROOT}/.env"
  qa4_load_dotenv_file "${QA4_INFRA_DIR}/.env"
}

qa4_load_dotenv_files
: "${QA4_DATA_ROOT:=/opt/qa4_data}"
: "${QA4_LOG_DIR:=/opt/qa4_logs}"

qa4_assert_data_root() {
  [[ -n "${QA4_DATA_ROOT}" ]] || qa4_die "QA4_DATA_ROOT 为空"
  [[ "${QA4_DATA_ROOT}" == /* ]] || qa4_die "QA4_DATA_ROOT 必须是绝对路径: ${QA4_DATA_ROOT}"
  [[ "${QA4_DATA_ROOT}" != "/" ]] || qa4_die "QA4_DATA_ROOT 不能是 /"
}

qa4_assert_container_name() {
  local name="${1:-}"
  [[ -n "$name" ]] || qa4_die "容器名为空"
  [[ "$name" == qa4* ]] || qa4_die "拒绝非 qa4 前缀容器名: ${name}"
}

qa4_require_env_file_mode() {
  local f mode
  for f in "${QA4_ROOT}/.env" "${QA4_INFRA_DIR}/.env"; do
    if [[ -e "$f" ]]; then
      mode="$(stat -c '%a' "$f" 2>/dev/null || stat -f '%OLp' "$f")"
      if [[ "$mode" != "600" ]]; then
        qa4_die ".env 权限必须为 600（当前 ${mode}）: ${f}"
      fi
    fi
  done
}

qa4_require_mem_limit() {
  # $1 = 变量名，如 QA4_ES_MEM_LIMIT
  local var="$1"
  local val="${!var:-}"
  if [[ -z "$val" || "$val" == "0" ]]; then
    if [[ "${QA4_ALLOW_NO_MEM_LIMIT:-}" == "1" ]]; then
      echo "WARN: ${var} 为空或 0；已设置 QA4_ALLOW_NO_MEM_LIMIT=1，允许继续" >&2
      return 0
    fi
    qa4_die "${var} 必须设置为非空且非 0（服务器禁止不限制内存）；测试可设 QA4_ALLOW_NO_MEM_LIMIT=1"
  fi
}

qa4_print_runtime_settings() {
  echo "生效设置（不含密码）:"
  echo "  QA4_DATA_ROOT=${QA4_DATA_ROOT}"
  echo "  QA4_LOG_DIR=${QA4_LOG_DIR}"
  echo "  QA4_ES_DATA_DIR=${QA4_ES_DATA_DIR:-}"
  echo "  QA4_ES_HEAP=${QA4_ES_HEAP:-2g}"
  echo "  QA4_ES_MEM_LIMIT=${QA4_ES_MEM_LIMIT:-}"
  echo "  QA4_NEO4J_HEAP=${QA4_NEO4J_HEAP:-1G}"
  echo "  QA4_NEO4J_PAGECACHE=${QA4_NEO4J_PAGECACHE:-512M}"
  echo "  QA4_NEO4J_MEM_LIMIT=${QA4_NEO4J_MEM_LIMIT:-}"
}

qa4_ensure_data_dirs() {
  qa4_assert_data_root
  mkdir -p "${QA4_DATA_ROOT}/es_data" \
           "${QA4_DATA_ROOT}/import_src" \
           "${QA4_LOG_DIR}"
  # ES 官方镜像默认 uid=1000；Neo4j 使用命名卷，不在此创建/chown 宿主目录
  if [[ "$(id -u)" -eq 0 ]]; then
    chown -R 1000:1000 "${QA4_DATA_ROOT}/es_data"
  else
    chown -R 1000:1000 "${QA4_DATA_ROOT}/es_data" 2>/dev/null || \
      echo "WARN: 无法 chown es_data 为 1000:1000，请确认目录属主" >&2
  fi
  export QA4_ES_DATA_DIR="${QA4_ES_DATA_DIR:-${QA4_DATA_ROOT}/es_data}"
  export QA4_LOG_DIR
  export QA4_DATA_ROOT
}

qa4_port_in_use() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -ltn "sport = :${port}" 2>/dev/null | tail -n +2 | grep -q .
  elif command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1
  else
    return 1
  fi
}

qa4_container_exists() {
  local name="$1"
  qa4_assert_container_name "$name"
  docker ps -a --filter "name=^/${name}$" --format '{{.Names}}' | grep -qx "$name"
}

qa4_container_running() {
  local name="$1"
  qa4_assert_container_name "$name"
  docker ps --filter "name=^/${name}$" --format '{{.Names}}' | grep -qx "$name"
}

qa4_refuse_port_conflict() {
  local port="$1"
  local expect_container="$2"
  qa4_assert_container_name "$expect_container"
  if ! qa4_port_in_use "$port"; then
    return 0
  fi
  if qa4_container_running "$expect_container"; then
    return 0
  fi
  qa4_die "端口 ${port} 已被占用，且容器 ${expect_container} 未在运行（拒绝与现有服务冲突）"
}

qa4_refuse_foreign_container_name() {
  local name="$1"
  qa4_assert_container_name "$name"
  if ! qa4_container_exists "$name"; then
    return 0
  fi
  local project
  project="$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' "$name" 2>/dev/null || true)"
  if [[ -n "$project" && "$project" != "qa4" ]]; then
    qa4_die "容器名 ${name} 已被 compose 项目 '${project}' 占用（拒绝）"
  fi
}
