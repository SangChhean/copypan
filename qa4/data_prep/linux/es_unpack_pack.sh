#!/usr/bin/env bash
# 解压 PanAI4.0 ES 数据包到 Dest，并按包内 SHA256SUMS.txt 逐文件核对。
# 不连接 ES。Dest 已存在且非空则拒绝（无覆盖开关）。
# zip 路径作参数，不依赖固定文件名。
# 用法：
#   bash ./es_unpack_pack.sh /path/to/PanAI4.0_ES数据包_xxxx.zip
#   bash ./es_unpack_pack.sh /path/to/pack.zip /opt/qa4_data/import_src
#   bash ./es_unpack_pack.sh /path/to/renamed.zip /opt/qa4_data/import_src <expected_sha256>
set -euo pipefail
# shellcheck source=_common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

# 154 = zip 内文件条目数；153 = SHA256SUMS.txt 有效清单行数（均可被环境变量覆盖）
EXPECTED_ZIP_ENTRIES="${EXPECTED_ZIP_ENTRIES:-154}"
EXPECTED_SUMS_ENTRIES="${EXPECTED_SUMS_ENTRIES:-153}"
MANIFEST_PATH="${QA4_ROOT}/docs/DATA_MANIFEST.md"

ZIP="${1:-}"
DEST="${2:-${QA4_DATA_ROOT}/import_src}"
EXPECTED_SHA="${3:-}"

[[ -n "$ZIP" ]] || qa4_die "用法: $0 <zip路径> [dest] [expected_sha256]"
[[ -f "$ZIP" ]] || qa4_die "找不到 zip: ${ZIP}"

qa4_require_env_file_mode
qa4_ensure_data_dirs
mkdir -p "$QA4_LOG_DIR"
ts="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${QA4_LOG_DIR}/qa4_unpack_${ts}.log"

log() {
  local line
  line="[$(date '+%Y-%m-%d %H:%M:%S')] $*"
  echo "$line"
  printf '%s\n' "$line" >>"$LOG_FILE"
}

: >"$LOG_FILE"

if [[ -d "$DEST" ]] && [[ -n "$(ls -A "$DEST" 2>/dev/null || true)" ]]; then
  log "Dest 已存在且非空，拒绝解压（无覆盖）: ${DEST}"
  exit 2
fi

want_sha="$(echo -n "${EXPECTED_SHA}" | tr '[:lower:]' '[:upper:]')"
if [[ -z "$want_sha" ]]; then
  [[ -f "$MANIFEST_PATH" ]] || qa4_die "找不到 DATA_MANIFEST.md: ${MANIFEST_PATH}"
  zip_leaf="$(basename "$ZIP")"
  want_sha="$(
    awk -v leaf="$zip_leaf" '
      index($0, leaf) {
        if (match($0, /[0-9A-Fa-f]{64}/)) {
          print toupper(substr($0, RSTART, RLENGTH))
          exit
        }
      }
    ' "$MANIFEST_PATH"
  )"
  [[ -n "$want_sha" ]] || qa4_die "无法从 DATA_MANIFEST.md 解析该 zip 的 SHA256（改名后请传第 3 参数）: ${zip_leaf}"
fi

log "计算 zip SHA256: ${ZIP}"
actual_sha="$(sha256sum "$ZIP" | awk '{print toupper($1)}')"
log "zip SHA256 = ${actual_sha}"
if [[ "$actual_sha" != "$want_sha" ]]; then
  log "SHA256 不一致，已中止。期望=${want_sha} 实际=${actual_sha}"
  exit 3
fi
log "SHA256 与期望一致。"
log "期望 zip 条目数=${EXPECTED_ZIP_ENTRIES} 期望清单条数=${EXPECTED_SUMS_ENTRIES}"

export EXPECTED_ZIP_ENTRIES EXPECTED_SUMS_ENTRIES
python3 - "$ZIP" "$DEST" "$LOG_FILE" <<'PY'
import hashlib, os, sys, zipfile
from pathlib import Path

zip_path = Path(sys.argv[1])
dest = Path(sys.argv[2])
log_path = Path(sys.argv[3])
expect_zip = int(os.environ.get("EXPECTED_ZIP_ENTRIES", "154"))
expect_sums = int(os.environ.get("EXPECTED_SUMS_ENTRIES", "153"))

def log(msg: str) -> None:
    print(msg, flush=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")

dest.mkdir(parents=True, exist_ok=True)
if any(p.is_file() for p in dest.rglob("*")):
    log(f"Dest 在解压前已有文件，拒绝: {dest}")
    sys.exit(2)

with zipfile.ZipFile(zip_path, "r") as zf:
    infos = [i for i in zf.infolist() if not i.is_dir()]
    entry_count = len(infos)
    log(f"zip 文件条目数={entry_count}")
    if entry_count != expect_zip:
        log(f"zip 条目数不符: got={entry_count} expect={expect_zip}")
        sys.exit(8)
    dest_res = dest.resolve()
    for info in zf.infolist():
        target = (dest / info.filename).resolve()
        if not str(target).startswith(str(dest_res)):
            log(f"拒绝可疑路径: {info.filename}")
            sys.exit(4)
    zf.extractall(dest)

files = [p for p in dest.rglob("*") if p.is_file()]
log(f"解压后文件数={len(files)}")
if len(files) != entry_count:
    log(f"解压后文件数与 zip 条目数不一致: {len(files)} != {entry_count}")
    sys.exit(5)

sums = None
for cand in [dest / "SHA256SUMS.txt", *dest.rglob("SHA256SUMS.txt")]:
    if cand.is_file():
        sums = cand
        break
if sums is None:
    log("未找到解压后的 SHA256SUMS.txt")
    sys.exit(6)

base = sums.parent
bad = 0
checked = 0
for line in sums.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    parts = line.split()
    if len(parts) < 2:
        continue
    digest, rel = parts[0], parts[-1].lstrip("*")
    path = base / rel
    checked += 1
    if not path.is_file():
        log(f"SHA_MISSING {rel}")
        bad += 1
        continue
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    got = h.hexdigest()
    if got.lower() != digest.lower():
        log(f"SHA_FAIL {rel}")
        bad += 1

if checked != expect_sums:
    log(f"SHA256SUMS 条目数不符: checked={checked} expect={expect_sums}")
    sys.exit(9)

total_bytes = sum(p.stat().st_size for p in files)
log(f"核对文件数={checked} 不一致={bad}")
log(f"汇总: 文件数={len(files)} 总字节={total_bytes} 核对结果={'OK' if bad == 0 else 'FAIL'}")
if bad != 0:
    sys.exit(7)
log("解压与 SHA 核对全部通过。")
sys.exit(0)
PY

log "完成。日志: ${LOG_FILE}"
