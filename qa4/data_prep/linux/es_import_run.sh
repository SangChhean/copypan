#!/usr/bin/env bash
# 包装调用 es_import.py：交互取密码写入本进程 QA4_ES_PASSWORD，结束清除。
# 密码用 read -rs；仅放入进程环境变量，不出现在命令行/日志/ps 参数中。
# 日志目录：QA4_LOG_DIR（默认 /opt/qa4_logs），由 es_import.py 读取该环境变量。
# 用法：
#   ./es_import_run.sh
#   ./es_import_run.sh --dry-run
#   ./es_import_run.sh --only panai4_hymns,panai4_bible
#   ./es_import_run.sh --force
#   ./es_import_run.sh --data-root /opt/qa4_data/import_src/es/data
set -euo pipefail
# shellcheck source=_common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

PY_SCRIPT="${QA4_DATA_PREP_DIR}/es_import.py"
[[ -f "$PY_SCRIPT" ]] || qa4_die "找不到 es_import.py: ${PY_SCRIPT}"

qa4_require_env_file_mode
qa4_ensure_data_dirs
mkdir -p "$QA4_LOG_DIR"
export QA4_LOG_DIR

DATA_ROOT="${QA4_DATA_ROOT}/import_src/es/data"
ONLY=""
FORCE=0
DRY_RUN=0
OFFLINE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --data-root)
      DATA_ROOT="${2:-}"
      shift 2
      ;;
    --only)
      ONLY="${2:-}"
      shift 2
      ;;
    --force)
      FORCE=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --offline)
      OFFLINE=1
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      echo "用法: $0 [--data-root DIR] [--only a,b] [--force] [--dry-run] [--offline]"
      exit 0
      ;;
    *)
      qa4_die "未知参数: $1"
      ;;
  esac
done

[[ -d "$DATA_ROOT" ]] || qa4_die "数据目录不存在: ${DATA_ROOT}（请先运行 es_unpack_pack.sh）"

py_args=( "$PY_SCRIPT" --data-root "$DATA_ROOT" )
if [[ -n "$ONLY" ]]; then
  py_args+=( --only )
  IFS=',' read -r -a names <<<"$ONLY"
  for n in "${names[@]}"; do
    n="$(echo "$n" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    [[ -n "$n" ]] && py_args+=( "$n" )
  done
fi
[[ "$FORCE" -eq 1 ]] && py_args+=( --force )
[[ "$DRY_RUN" -eq 1 ]] && py_args+=( --dry-run )
[[ "$OFFLINE" -eq 1 ]] && py_args+=( --offline )

need_password=1
if [[ "$DRY_RUN" -eq 1 || "$OFFLINE" -eq 1 ]]; then
  need_password=0
fi

# shellcheck disable=SC2329  # invoked via trap
cleanup() {
  unset QA4_ES_PASSWORD || true
}
trap cleanup EXIT

if [[ "$need_password" -eq 1 ]]; then
  echo "请输入 QA4_ES_PASSWORD（输入不可见）:"
  read -rs QA4_ES_PASSWORD
  echo
  [[ -n "${QA4_ES_PASSWORD}" ]] || qa4_die "密码为空，已中止。"
  export QA4_ES_PASSWORD
fi

# 打印参数时不含密码（密码只在环境变量中）
echo "调用: python3 ${py_args[*]}"
python3 "${py_args[@]}"
code=$?
exit "$code"
