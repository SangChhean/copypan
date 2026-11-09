# 包装调用 es_verify.py：分别交互取 QA4_ES_PASSWORD 与 OLD_ES_PASSWORD，结束清除。
# 不使用 2>&1 管道；报告由 Python 写到 G:\PanAI4.0专用\logs\qa4_verify_<时间戳>.md/.json。
# 用法：
#   .\es_verify_run.ps1 -OldUser elastic
#   .\es_verify_run.ps1 -Only hymns,bible -SkipKnn
#   .\es_verify_run.ps1 -SkipBm25 -SkipKnn

[CmdletBinding()]
param(
  [string]$OldUser = "elastic",
  [string]$Only = "",
  [switch]$SkipBm25,
  [switch]$SkipKnn,
  [string]$Qa4Url = "http://127.0.0.1:9202",
  [string]$OldUrl = "http://127.0.0.1:9200"
)

$ErrorActionPreference = "Stop"
$OutputEncoding = New-Object System.Text.UTF8Encoding($false)

$PyScript = Join-Path $PSScriptRoot "es_verify.py"
if (-not (Test-Path -LiteralPath $PyScript)) {
  Write-Output ("找不到 es_verify.py: " + $PyScript)
  exit 1
}

function Read-SecretEnv([string]$Prompt) {
  $secure = Read-Host -AsSecureString $Prompt
  if (-not $secure -or $secure.Length -eq 0) {
    Write-Output "密码为空，已中止。"
    return $null
  }
  $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
  try {
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    if ([string]::IsNullOrEmpty($plain)) {
      Write-Output "密码为空，已中止。"
      return $null
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

$pyArgs = @(
  $PyScript,
  "--old-user", $OldUser,
  "--qa4-url", $Qa4Url,
  "--old-url", $OldUrl
)

if ($Only -and $Only.Trim().Length -gt 0) {
  $names = @()
  foreach ($part in ($Only -split "[,\s]+")) {
    if ($part -and $part.Trim().Length -gt 0) { $names += $part.Trim() }
  }
  if ($names.Count -gt 0) {
    $pyArgs += "--only"
    $pyArgs += $names
  }
}
if ($SkipBm25) { $pyArgs += "--skip-bm25" }
if ($SkipKnn) { $pyArgs += "--skip-knn" }

$qa4Plain = Read-SecretEnv "请输入 QA4_ES_PASSWORD（qa4-es，输入不可见）"
if ($null -eq $qa4Plain) { exit 1 }
$oldPlain = Read-SecretEnv "请输入 OLD_ES_PASSWORD（旧 ES / elasticsearch8，输入不可见）"
if ($null -eq $oldPlain) {
  $qa4Plain = $null
  exit 1
}

$env:QA4_ES_PASSWORD = $qa4Plain
$env:OLD_ES_PASSWORD = $oldPlain
$qa4Plain = $null
$oldPlain = $null

try {
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
  Remove-Item Env:QA4_ES_PASSWORD -ErrorAction SilentlyContinue
  Remove-Item Env:OLD_ES_PASSWORD -ErrorAction SilentlyContinue
}
