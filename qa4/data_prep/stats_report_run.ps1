# 包装调用 stats_report.py：交互取 ES/Neo4j 密码写入本进程环境变量，结束清除。
# 密码用 Read-Host -AsSecureString；不打印、不落盘。
# 日志与报告写到 G:\PanAI4.0专用\统计\
# 用法：
#   .\stats_report_run.ps1
#   .\stats_report_run.ps1 -SelfTest
#   .\stats_report_run.ps1 -OutDir "G:\PanAI4.0专用\统计"

[CmdletBinding()]
param(
  [string]$OutDir = "G:\PanAI4.0专用\统计",
  [string]$EsUrl = "http://127.0.0.1:9202",
  [string]$Neo4jUri = "bolt://127.0.0.1:7689",
  [switch]$SelfTest
)

$ErrorActionPreference = "Stop"
$OutputEncoding = New-Object System.Text.UTF8Encoding($false)

$PyScript = Join-Path $PSScriptRoot "stats_report.py"
if (-not (Test-Path -LiteralPath $PyScript)) {
  Write-Output ("找不到 stats_report.py: " + $PyScript)
  exit 1
}

if ($SelfTest) {
  & python $PyScript --self-test
  exit $LASTEXITCODE
}

function Read-SecretEnv([string]$Prompt) {
  $secure = Read-Host -AsSecureString $Prompt
  if (-not $secure -or $secure.Length -eq 0) {
    throw "密码为空，已中止。"
  }
  $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
  try {
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    if ([string]::IsNullOrEmpty($plain)) {
      throw "密码为空，已中止。"
    }
    return $plain
  }
  finally {
    if ($bstr -ne [IntPtr]::Zero) {
      [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
    $secure = $null
  }
}

if (-not (Test-Path -LiteralPath $OutDir)) {
  New-Item -ItemType Directory -Path $OutDir | Out-Null
}

$esPlain = $null
$neoPlain = $null
try {
  $esPlain = Read-SecretEnv "请输入 QA4_ES_PASSWORD（qa4-es，输入不可见）"
  $neoPlain = Read-SecretEnv "请输入 QA4_NEO4J_PASSWORD（qa4-neo4j，输入不可见）"
  $env:QA4_ES_PASSWORD = $esPlain
  $env:QA4_NEO4J_PASSWORD = $neoPlain
  $esPlain = $null
  $neoPlain = $null

  $pyArgs = @(
    $PyScript,
    "--es-url", $EsUrl,
    "--neo4j-uri", $Neo4jUri,
    "--out-dir", $OutDir
  )
  Write-Output ("调用: python " + ($pyArgs -join " "))
  $prevEap = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  & python @pyArgs
  $code = $LASTEXITCODE
  $ErrorActionPreference = $prevEap
  if ($null -eq $code) { $code = 0 }
  exit $code
}
finally {
  $esPlain = $null
  $neoPlain = $null
  Remove-Item Env:QA4_ES_PASSWORD -ErrorAction SilentlyContinue
  Remove-Item Env:QA4_NEO4J_PASSWORD -ErrorAction SilentlyContinue
}
