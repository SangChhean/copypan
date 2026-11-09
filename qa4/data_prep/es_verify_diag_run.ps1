# 包装调用 es_verify_diag.py：分别交互取 QA4_ES_PASSWORD 与 OLD_ES_PASSWORD，结束清除。
# 不使用 2>&1；报告由 Python 写到 G:\PanAI4.0专用\logs\qa4_verify_diag_<时间戳>.md/.json。
# 用法：
#   .\es_verify_diag_run.ps1 -OldUser elastic
#   .\es_verify_diag_run.ps1 -SkipKnn

[CmdletBinding()]
param(
  [string]$OldUser = "elastic",
  [switch]$SkipContent,
  [switch]$SkipKnn,
  [switch]$SkipBm25,
  [string]$Qa4Url = "http://127.0.0.1:9202",
  [string]$OldUrl = "http://127.0.0.1:9200"
)

$ErrorActionPreference = "Stop"
$OutputEncoding = New-Object System.Text.UTF8Encoding($false)

$PyScript = Join-Path $PSScriptRoot "es_verify_diag.py"
if (-not (Test-Path -LiteralPath $PyScript)) {
  Write-Output ("找不到 es_verify_diag.py: " + $PyScript)
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
if ($SkipContent) { $pyArgs += "--skip-content" }
if ($SkipKnn) { $pyArgs += "--skip-knn" }
if ($SkipBm25) { $pyArgs += "--skip-bm25" }

$qa4Plain = Read-SecretEnv "请输入 QA4_ES_PASSWORD（qa4-es，输入不可见）"
if ($null -eq $qa4Plain) { exit 1 }
$oldPlain = Read-SecretEnv "请输入 OLD_ES_PASSWORD（旧 ES，输入不可见）"
if ($null -eq $oldPlain) { $qa4Plain = $null; exit 1 }

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
