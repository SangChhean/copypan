# 交互输入密码后，用 docker compose 启动 qa4-neo4j。
# 密码仅存在于本进程环境变量 QA4_NEO4J_PASSWORD，结束时清除；不写文件、不打印。
# 注意：若卷 qa4_neo4j_data 已由 dump 初始化过，请输入与当初设库时相同的密码；
# Neo4j 对已初始化数据目录不会因 NEO4J_AUTH 重置密码。

$ErrorActionPreference = "Stop"

$Container = "qa4-neo4j"
$ComposeFile = Join-Path $PSScriptRoot "..\infra\docker-compose.neo4j.yml"
$ComposeFile = [System.IO.Path]::GetFullPath($ComposeFile)
$ProjectDir = Split-Path -Parent $ComposeFile

if (-not (Test-Path -LiteralPath $ComposeFile)) {
  Write-Output "找不到 compose 文件: $ComposeFile"
  exit 1
}

Write-Output "提示：重建或重启已初始化的 qa4-neo4j 时，请输入与原来相同的密码（数据卷内已存认证，NEO4J_AUTH 对已初始化库不生效）。"
$secure = Read-Host -AsSecureString "请输入 QA4_NEO4J_PASSWORD（输入不可见）"
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
  $env:QA4_NEO4J_PASSWORD = $plain
  $plain = $null
}
finally {
  if ($bstr -ne [IntPtr]::Zero) {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
  }
  $secure = $null
}

try {
  Write-Output "启动 compose 服务 qa4-neo4j ..."
  $prevEap = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  docker compose -f $ComposeFile --project-directory $ProjectDir up -d qa4-neo4j
  $upCode = $LASTEXITCODE
  $ErrorActionPreference = $prevEap
  if ($upCode -ne 0) {
    Write-Output "docker compose up 失败，exit=$upCode"
    exit $upCode
  }

  Write-Output "等待容器日志出现 Started ..."
  $deadline = (Get-Date).AddMinutes(3)
  $ok = $false
  while ((Get-Date) -lt $deadline) {
    # 捕获 logs 时临时 Continue；避免在 Stop 下对原生命令使用 2>&1
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $logs = docker logs $Container | Out-String
    $null = $LASTEXITCODE
    $ErrorActionPreference = $prevEap
    if ($logs -match "Started") {
      $ok = $true
      break
    }
    Start-Sleep -Seconds 2
  }

  if (-not $ok) {
    Write-Output "超时：未在日志中看到 Started。请自行检查: docker logs $Container"
    exit 3
  }

  Write-Output "qa4-neo4j 已启动（日志含 Started）。Browser http://127.0.0.1:7476  Bolt bolt://127.0.0.1:7689"
  exit 0
}
finally {
  Remove-Item Env:QA4_NEO4J_PASSWORD -ErrorAction SilentlyContinue
}
