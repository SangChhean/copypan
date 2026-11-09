# 解压 PanAI4.0 ES 数据包到 Dest，并按包内 SHA256SUMS.txt 逐文件核对。
# 不连接 ES。Dest 已存在且非空则拒绝（无覆盖开关）。
# 用法：
#   .\es_unpack_pack.ps1
#   .\es_unpack_pack.ps1 -Zip "G:\...\PanAI4.0_ES数据包_20261107.zip" -Dest "G:\...\qa4_import_src"

[CmdletBinding()]
param(
  [string]$Zip = "G:\PanAI4.0专用\数据包\PanAI4.0_ES数据包_20261107.zip",
  [string]$Dest = "G:\PanAI4.0专用\qa4_import_src",
  [string]$ExpectedSha = ""
)

$ErrorActionPreference = "Stop"
$OutputEncoding = New-Object System.Text.UTF8Encoding($false)

$ManifestPath = Join-Path $PSScriptRoot "..\docs\DATA_MANIFEST.md"
$ManifestPath = [System.IO.Path]::GetFullPath($ManifestPath)
$LogDir = "G:\PanAI4.0专用\logs"
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = Join-Path $LogDir ("qa4_unpack_" + $ts + ".log")

function Write-Log([string]$Message) {
  $line = ("[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message)
  Write-Output $line
  Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8
}

if (-not (Test-Path -LiteralPath $LogDir)) {
  New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}
# 先建空日志，便于后续失败也能查
"" | Set-Content -LiteralPath $LogFile -Encoding UTF8

if (-not (Test-Path -LiteralPath $Zip)) {
  Write-Log ("找不到 zip: " + $Zip)
  exit 1
}

if (Test-Path -LiteralPath $Dest) {
  $prevEap = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  $kids = @(Get-ChildItem -LiteralPath $Dest -Force -ErrorAction SilentlyContinue)
  $ErrorActionPreference = $prevEap
  if ($kids.Count -gt 0) {
    Write-Log ("Dest 已存在且非空，拒绝解压（无覆盖）: " + $Dest)
    exit 2
  }
}

# 解析期望 SHA
$wantSha = $ExpectedSha.Trim().ToUpperInvariant()
if (-not $wantSha) {
  if (-not (Test-Path -LiteralPath $ManifestPath)) {
    Write-Log ("找不到 DATA_MANIFEST.md: " + $ManifestPath)
    exit 1
  }
  $manifestText = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8
  $zipLeaf = [System.IO.Path]::GetFileName($Zip)
  $m = [regex]::Match(
    $manifestText,
    [regex]::Escape($zipLeaf) + "[^`r`n]*?`\|[^`|]*`\|[^`|]*`\|\s*`([0-9A-Fa-f]{64})`\s*`\|"
  )
  if (-not $m.Success) {
    # 宽松：在含 zip 名的行里找 64 位十六进制
    foreach ($line in ($manifestText -split "`r?`n")) {
      if ($line -like ("*" + $zipLeaf + "*")) {
        $m2 = [regex]::Match($line, "([0-9A-Fa-f]{64})")
        if ($m2.Success) { $wantSha = $m2.Groups[1].Value.ToUpperInvariant(); break }
      }
    }
  } else {
    $wantSha = $m.Groups[1].Value.ToUpperInvariant()
  }
  if (-not $wantSha) {
    Write-Log ("无法从 DATA_MANIFEST.md 解析该 zip 的 SHA256: " + $zipLeaf)
    exit 1
  }
}

Write-Log ("计算 zip SHA256: " + $Zip)
$actualSha = (Get-FileHash -LiteralPath $Zip -Algorithm SHA256).Hash.ToUpperInvariant()
Write-Log ("zip SHA256 = " + $actualSha)
if ($actualSha -ne $wantSha) {
  Write-Log ("SHA256 不一致，已中止。期望=" + $wantSha + " 实际=" + $actualSha)
  exit 3
}
Write-Log "SHA256 与期望一致。"

# Python 解压 + 条目数核对 + SHA256SUMS 逐文件核对
$py = @'
import hashlib, sys, zipfile
from pathlib import Path

zip_path = Path(sys.argv[1])
dest = Path(sys.argv[2])
log_path = Path(sys.argv[3])

def log(msg: str) -> None:
    line = msg
    print(line, flush=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")

dest.mkdir(parents=True, exist_ok=True)
# 若在检查后被并行写入导致非空，仍拒绝
existing = [p for p in dest.rglob("*") if p.is_file() or (p.is_dir() and any(p.iterdir()))]
# only refuse if any file exists under dest
if any(p.is_file() for p in dest.rglob("*")):
    log(f"Dest 在解压前已有文件，拒绝: {dest}")
    sys.exit(2)

with zipfile.ZipFile(zip_path, "r") as zf:
    infos = [i for i in zf.infolist() if not i.is_dir()]
    entry_count = len(infos)
    log(f"zip 文件条目数={entry_count}")
    # 安全解压：防 zip-slip
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

# 找 SHA256SUMS.txt（通常在包根）
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

total_bytes = sum(p.stat().st_size for p in files)
log(f"核对文件数={checked} 不一致={bad}")
log(f"汇总: 文件数={len(files)} 总字节={total_bytes} 核对结果={'OK' if bad == 0 else 'FAIL'}")
if bad != 0:
    sys.exit(7)
log("解压与 SHA 核对全部通过。")
sys.exit(0)
'@

$tmpPy = Join-Path $env:TEMP ("qa4_unpack_" + $ts + ".py")
[System.IO.File]::WriteAllText($tmpPy, $py, (New-Object System.Text.UTF8Encoding $false))

Write-Log ("开始解压到: " + $Dest)
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& python $tmpPy $Zip $Dest $LogFile
$code = $LASTEXITCODE
$ErrorActionPreference = $prevEap
Remove-Item -LiteralPath $tmpPy -Force -ErrorAction SilentlyContinue

if ($code -ne 0) {
  Write-Log ("解压/核对失败，exit=" + $code)
  # 半截结果：若失败且 Dest 下有文件，明确报告（不自动删除，避免误伤用户数据）
  if (Test-Path -LiteralPath $Dest) {
    $left = @(Get-ChildItem -LiteralPath $Dest -Recurse -File -Force -ErrorAction SilentlyContinue)
    if ($left.Count -gt 0) {
      Write-Log ("注意: Dest 中可能留有部分解压结果，文件数=" + $left.Count + " 路径=" + $Dest + " （请人工清理后重试）")
    }
  }
  exit $code
}

Write-Log ("完成。日志: " + $LogFile)
exit 0
