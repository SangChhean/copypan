# 包装调用 es_import.py：交互取密码写入本进程 QA4_ES_PASSWORD，结束清除。
# 不把 python 输出经 2>&1 再管道；日志由 es_import.py 写文件。
# 用法：
#   .\es_import_run.ps1 -DryRun
#   .\es_import_run.ps1 -Only panai4_hymns,panai4_bible
#   .\es_import_run.ps1 -Force

[CmdletBinding()]
param(
  [string]$DataRoot = "G:\PanAI4.0专用\qa4_import_src\es\data",
  [string]$Only = "",
  [switch]$Force,
  [switch]$DryRun,
  [switch]$Offline
)

$ErrorActionPreference = "Stop"
$OutputEncoding = New-Object System.Text.UTF8Encoding($false)

$PyScript = Join-Path $PSScriptRoot "es_import.py"
if (-not (Test-Path -LiteralPath $PyScript)) {
  Write-Output ("找不到 es_import.py: " + $PyScript)
  exit 1
}

if (-not (Test-Path -LiteralPath $DataRoot)) {
  Write-Output ("数据目录不存在: " + $DataRoot)
  Write-Output "请先运行 es_unpack_pack.ps1 解压数据包。"
  exit 1
}

$pyArgs = @($PyScript, "--data-root", $DataRoot)

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

if ($Force) { $pyArgs += "--force" }
if ($DryRun) { $pyArgs += "--dry-run" }
if ($Offline) {
  if (-not $DryRun) { $pyArgs += "--dry-run" }
  $pyArgs += "--offline"
}

# offline/dry-run 不需要密码
$needPassword = -not ($DryRun -or $Offline)
if ($needPassword) {
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
}

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
}
