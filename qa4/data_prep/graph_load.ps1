# 将 neo4j.dump 载入命名卷 qa4_neo4j_data（一次性容器，不启动正式服务）。
# 用法：
#   .\graph_load.ps1
#   .\graph_load.ps1 -DumpDir "G:\PanAI4.0专用\图谱上线" -Force
# 不需要密码。-Force 时会移除已有 qa4-neo4j 容器与 qa4_neo4j_data 卷后重建。

[CmdletBinding()]
param(
  [string]$DumpDir = "G:\PanAI4.0专用\图谱上线",
  [switch]$Force
)

$ErrorActionPreference = "Stop"

$ExpectedSha = "B5B0C10C657E0FF03309A6D21603DC11B3152D66037F499EAD266948721089C4"
$Image = "neo4j:5.26.28"
$Volume = "qa4_neo4j_data"
$Container = "qa4-neo4j"
$DbName = "neo4j"

function Invoke-NativeCapture {
  param([scriptblock]$Script)
  $prev = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    $output = & $Script
    $code = $LASTEXITCODE
  }
  finally {
    $ErrorActionPreference = $prev
  }
  return @{ Output = $output; ExitCode = $code }
}

function Test-DockerVolumeExists([string]$Name) {
  $r = Invoke-NativeCapture { docker volume ls --format "{{.Name}}" }
  return [bool](@($r.Output) | Where-Object { $_ -eq $Name })
}

function Test-DockerVolumeNonEmpty([string]$Name) {
  if (-not (Test-DockerVolumeExists $Name)) { return $false }
  $r = Invoke-NativeCapture {
    docker run --rm --volume "${Name}:/data:ro" $Image ls -A /data
  }
  if ($r.ExitCode -ne 0) {
    throw "无法检查卷内容: $Name (docker run ls 失败)"
  }
  $items = @($r.Output | Where-Object { $_ -and $_.ToString().Trim() -ne "" })
  return ($items.Count -gt 0)
}

function Test-DockerContainerExists([string]$Name) {
  $r = Invoke-NativeCapture {
    docker ps -a --filter "name=^/${Name}$" --format "{{.Names}}"
  }
  return [bool](@($r.Output) | Where-Object { $_ })
}

$dumpPath = Join-Path $DumpDir "neo4j.dump"
if (-not (Test-Path -LiteralPath $dumpPath)) {
  Write-Output "找不到 dump: $dumpPath"
  exit 1
}

Write-Output "核对 dump SHA256 ..."
$actualSha = (Get-FileHash -LiteralPath $dumpPath -Algorithm SHA256).Hash.ToUpperInvariant()
if ($actualSha -ne $ExpectedSha) {
  Write-Output "SHA256 不一致，已中止。"
  Write-Output "  期望: $ExpectedSha"
  Write-Output "  实际: $actualSha"
  exit 1
}
Write-Output "SHA256 一致。"

$containerExists = Test-DockerContainerExists $Container
$volumeExists = Test-DockerVolumeExists $Volume
$volumeNonEmpty = $false
if ($volumeExists) {
  $volumeNonEmpty = Test-DockerVolumeNonEmpty $Volume
}

if (-not $Force) {
  if ($containerExists) {
    Write-Output "已存在容器 '$Container'。未指定 -Force，拒绝继续（本脚本不会自动删除）。"
    exit 2
  }
  if ($volumeExists -and $volumeNonEmpty) {
    Write-Output "卷 '$Volume' 已存在且非空。未指定 -Force，拒绝继续（本脚本不会自动删除）。"
    exit 2
  }
}

if ($Force) {
  if ($containerExists) {
    Write-Output "-Force: 移除容器 $Container ..."
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    docker rm -f $Container | Out-Null
    $ErrorActionPreference = $prevEap
  }
  if ($volumeExists) {
    Write-Output "-Force: 删除卷 $Volume ..."
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    docker volume rm $Volume | Out-Null
    $ErrorActionPreference = $prevEap
  }
}

if (-not (Test-DockerVolumeExists $Volume)) {
  Write-Output "创建卷 $Volume ..."
  $prevEap = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  docker volume create $Volume | Out-Null
  $ErrorActionPreference = $prevEap
}

Write-Output "一次性容器执行 neo4j-admin database load ($DbName) ..."
# 将目录挂到 /dump，load 从该路径读取 neo4j.dump
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
docker run --rm `
  --volume "${Volume}:/data" `
  --volume "${DumpDir}:/dump:ro" `
  $Image `
  neo4j-admin database load $DbName --from-path=/dump --overwrite-destination=true
$loadCode = $LASTEXITCODE
$ErrorActionPreference = $prevEap

if ($loadCode -ne 0) {
  Write-Output "load 失败，exit=$loadCode"
  exit $loadCode
}

Write-Output "load 完成。请再运行 graph_start.ps1 启动正式容器 qa4-neo4j。"
exit 0
