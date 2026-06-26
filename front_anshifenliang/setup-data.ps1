# 将 back_anshifenliang/data 链接到 front_anshifenliang（不重复存数据）
# 部署时运行一次；可用 DATA_SRC 覆盖数据源路径
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Src = if ($env:DATA_SRC) { $env:DATA_SRC } else { Join-Path (Split-Path $Root) "back_anshifenliang\data" }

if (-not (Test-Path $Src)) { throw "Data source not found: $Src" }

$files = @(
  "traditional_to_simplified.js", "simplified_to_traditional.js",
  "qu-bie-ci-exclusion-map.js", "hymns.js", "shi_ge.js", "shi_ge_fen_lei.js",
  "zhu_jie_wen_da.js", "cha_kan_zheng_pian.js", "jing_jie_wen_da.js",
  "xiao_bai_ke.js", "shu-ling-wen-da.js", "bible_verse.js", "jing_jie_zhu_shi.js",
  "styles.css", "content_view.html", "viewer_host.html", "favicon.ico"
)

foreach ($f in $files) {
  $dst = Join-Path $Root $f
  $srcFile = Join-Path $Src $f
  if (-not (Test-Path $srcFile)) {
    Write-Warning "skip missing: $f"
    continue
  }
  if (Test-Path $dst) {
    $item = Get-Item $dst -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
      Write-Host "already linked $f"
      continue
    }
    Remove-Item $dst -Force
  }
  cmd /c mklink /H "`"$dst`"" "`"$srcFile`""
  Write-Host "linked $f"
}

# private 目录 junction
$privateDst = Join-Path $Root "private"
$privateSrc = Join-Path $Src "private"
if (Test-Path $privateDst) {
  $item = Get-Item $privateDst -Force
  if (-not ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
    Remove-Item $privateDst -Recurse -Force
  }
}
if (-not (Test-Path $privateDst)) {
  cmd /c mklink /J "`"$privateDst`"" "`"$privateSrc`""
  Write-Host "linked private/"
}

Write-Host "Done. Data linked from $Src"
