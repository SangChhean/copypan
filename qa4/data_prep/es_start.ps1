# 构建并启动 qa4-es（交互输入密码；不打印、不落盘）。
# 用法：.\es_start.ps1
#       .\es_start.ps1 -DataDir "G:\PanAI4.0专用\qa4_es_data"

[CmdletBinding()]
param(
  [string]$DataDir = "G:\PanAI4.0专用\qa4_es_data"
)

$ErrorActionPreference = "Stop"

$Container = "qa4-es"
$ComposeFile = Join-Path $PSScriptRoot "..\infra\docker-compose.es.yml"
$ComposeFile = [System.IO.Path]::GetFullPath($ComposeFile)
$ProjectDir = Split-Path -Parent $ComposeFile

if (-not (Test-Path -LiteralPath $ComposeFile)) {
  Write-Output "找不到 compose 文件: $ComposeFile"
  exit 1
}

if (-not (Test-Path -LiteralPath $DataDir)) {
  Write-Output "创建数据目录: $DataDir"
  New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
}

$secure = Read-Host -AsSecureString "请输入 QA4_ES_PASSWORD（输入不可见）"
if (-not $secure -or $secure.Length -eq 0) {
  Write-Output "密码为空，已中止。"
  exit 1
}

$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
  $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
  if ([string]::IsNullOrEmpty($plain)) {
    Write-Output "密码为空，已中止。"
    exit 1
  }
  $env:QA4_ES_PASSWORD = $plain
  $plain = $null
}
finally {
  if ($bstr -ne [IntPtr]::Zero) {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
  }
  $secure = $null
}

$env:QA4_ES_DATA_DIR = $DataDir

try {
  Write-Output "docker compose up -d --build qa4-es ..."
  $prevEap = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  docker compose -f $ComposeFile --project-directory $ProjectDir up -d --build qa4-es
  $upCode = $LASTEXITCODE
  $ErrorActionPreference = $prevEap
  if ($upCode -ne 0) {
    Write-Output "docker compose up 失败，exit=$upCode"
    exit $upCode
  }

  Write-Output "等待 _cluster/health 变为 green 或 yellow（最多 5 分钟）..."
  $deadline = (Get-Date).AddMinutes(5)
  $ok = $false
  while ((Get-Date) -lt $deadline) {
    # 使用容器内 ELASTIC_PASSWORD，不在宿主机打印
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    docker exec $Container bash -c 'curl -s -u "elastic:${ELASTIC_PASSWORD}" http://localhost:9200/_cluster/health' | Out-File -FilePath "$env:TEMP\qa4_es_health.json" -Encoding utf8
    $healthCode = $LASTEXITCODE
    $ErrorActionPreference = $prevEap
    if ($healthCode -eq 0 -and (Test-Path -LiteralPath "$env:TEMP\qa4_es_health.json")) {
      $raw = Get-Content -LiteralPath "$env:TEMP\qa4_es_health.json" -Raw -Encoding utf8
      if ($raw -match '"status"\s*:\s*"(green|yellow)"') {
        $ok = $true
        Write-Output ("健康检查通过: status=" + $Matches[1])
        break
      }
    }
    Start-Sleep -Seconds 3
  }
  Remove-Item -LiteralPath "$env:TEMP\qa4_es_health.json" -Force -ErrorAction SilentlyContinue

  if (-not $ok) {
    Write-Output "超时：集群未达到 green/yellow。请检查: docker logs $Container"
    exit 3
  }

  Write-Output "qa4-es 已就绪。HTTP http://127.0.0.1:9202"
  exit 0
}
finally {
  Remove-Item Env:QA4_ES_PASSWORD -ErrorAction SilentlyContinue
  Remove-Item Env:QA4_ES_DATA_DIR -ErrorAction SilentlyContinue
}
