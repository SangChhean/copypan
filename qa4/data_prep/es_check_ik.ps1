# 对比 elasticsearch8 与 qa4-es 的 IK 插件/词典文件哈希，以及对同一批文本的分词结果。
# 要求 qa4-es 已启动。密码使用各自容器内环境变量，不打印。
# 中文经标准输入传入容器（UTF-8），不走命令行参数。

$ErrorActionPreference = "Stop"
$OutputEncoding = New-Object System.Text.UTF8Encoding($false)

$Src = "elasticsearch8"
$Dst = "qa4-es"

function Invoke-NativeCapture {
  param(
    [scriptblock]$Script
  )
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

function Assert-ContainerRunning([string]$Name) {
  $r = Invoke-NativeCapture { docker inspect -f "{{.State.Running}}" $Name }
  if ($r.ExitCode -ne 0 -or [string]$r.Output -ne "true") {
    Write-Output "容器未运行: $Name"
    exit 1
  }
}

function Get-FileHashMap([string]$Container, [string]$Dir) {
  # 避免裸 {} / ; 作为原生命令参数（PS 5.1 会把 {} 当脚本块）
  $r = Invoke-NativeCapture {
    docker exec $Container sh -c "find $Dir -type f -print0 | xargs -0 sha256sum"
  }
  if ($r.ExitCode -ne 0) {
    throw "无法读取哈希: $Container $Dir"
  }
  $map = @{}
  foreach ($line in @($r.Output)) {
    $s = [string]$line
    if (-not $s.Trim()) { continue }
    $hash = $s.Substring(0, 64).ToLowerInvariant()
    $name = Split-Path ($s.Substring(66).Trim()) -Leaf
    $map[$name] = $hash
  }
  return $map
}

function Get-AnalyzeTokens([string]$Container, [string]$Analyzer, [byte[]]$JsonUtf8) {
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = "docker"
  $psi.Arguments = "exec -i $Container bash -c `"curl -s -u elastic:`$ELASTIC_PASSWORD -H 'Content-Type: application/json; charset=UTF-8' --data-binary @- http://localhost:9200/_analyze`""
  $psi.RedirectStandardInput = $true
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError = $true
  $psi.UseShellExecute = $false
  $psi.CreateNoWindow = $true
  $p = [System.Diagnostics.Process]::Start($psi)
  $p.StandardInput.BaseStream.Write($JsonUtf8, 0, $JsonUtf8.Length)
  $p.StandardInput.Close()
  $ms = New-Object System.IO.MemoryStream
  $p.StandardOutput.BaseStream.CopyTo($ms)
  $err = $p.StandardError.ReadToEnd()
  $p.WaitForExit()
  if ($p.ExitCode -ne 0) {
    Write-Output ("_analyze 失败 container=" + $Container + " analyzer=" + $Analyzer)
    Write-Output $err
    exit 3
  }
  $raw = [System.Text.Encoding]::UTF8.GetString($ms.ToArray())
  $tokens = [regex]::Matches($raw, '"token"\s*:\s*"((?:\\.|[^"\\])*)"') | ForEach-Object {
    [System.Text.RegularExpressions.Regex]::Unescape($_.Groups[1].Value)
  }
  return ($tokens -join "`n")
}

Assert-ContainerRunning $Src
Assert-ContainerRunning $Dst

Write-Output "==== 文件 SHA256 对照 ===="
$mismatch = 0
foreach ($pair in @(
  @{ Path = "/usr/share/elasticsearch/plugins/analysis-ik"; Label = "plugins/analysis-ik" },
  @{ Path = "/usr/share/elasticsearch/config/analysis-ik"; Label = "config/analysis-ik" }
)) {
  Write-Output ("-- " + $pair.Label)
  $srcMap = Get-FileHashMap $Src $pair.Path
  $dstMap = Get-FileHashMap $Dst $pair.Path
  $all = @($srcMap.Keys + $dstMap.Keys) | Sort-Object -Unique
  foreach ($name in $all) {
    $a = $srcMap[$name]
    $b = $dstMap[$name]
    if ($a -ne $b) {
      Write-Output ("DIFF {0}: src={1} dst={2}" -f $name, $a, $b)
      $mismatch++
    } else {
      Write-Output ("OK   {0}" -f $name)
    }
  }
}
if ($mismatch -gt 0) {
  Write-Output ("文件哈希不一致 count=" + $mismatch)
  exit 2
}
Write-Output "文件哈希全部一致。"

Write-Output "==== 分词对照 (_analyze) ===="
$rDic = Invoke-NativeCapture {
  docker exec $Src head -n 20 /usr/share/elasticsearch/config/analysis-ik/pansearch.dic
}
if ($rDic.ExitCode -ne 0) { Write-Output "无法读取 pansearch.dic"; exit 1 }
$words = @()
foreach ($ln in @($rDic.Output)) {
  $t = ([string]$ln).Trim()
  if ($t) { $words += $t }
}
$fixed = @(
  "神的经纶与基督的身体",
  "生命的流与生命的供应",
  "三一神在信徒里面的运行",
  "召会是基督的身体",
  "那灵与我们的灵同证",
  "主日早晨的聚集",
  "职事信息里的真理亮光",
  "圣经恢复本的注解",
  "倪柝声与李常受的职事",
  "葡萄树与枝子的接枝"
)
$payloadText = (($words + $fixed) -join "`n")

# 用 Python 生成 UTF-8 JSON 字节（中文不经命令行参数）
$pyBuild = @'
import json, sys
analyzer = sys.argv[1]
text = sys.stdin.buffer.read().decode("utf-8")
sys.stdout.buffer.write(json.dumps({"analyzer": analyzer, "text": text}, ensure_ascii=False).encode("utf-8"))
'@
$tmpPy = Join-Path $env:TEMP "qa4_ik_build_json.py"
[System.IO.File]::WriteAllText($tmpPy, $pyBuild, (New-Object System.Text.UTF8Encoding $false))

$analyzeDiff = 0
foreach ($analyzer in @("ik_smart", "ik_max_word")) {
  Write-Output ("analyzer=" + $analyzer)
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = "python"
  $psi.Arguments = "`"$tmpPy`" $analyzer"
  $psi.RedirectStandardInput = $true
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError = $true
  $psi.UseShellExecute = $false
  $psi.CreateNoWindow = $true
  $pb = [System.Diagnostics.Process]::Start($psi)
  $textBytes = [System.Text.Encoding]::UTF8.GetBytes($payloadText)
  $pb.StandardInput.BaseStream.Write($textBytes, 0, $textBytes.Length)
  $pb.StandardInput.Close()
  $jms = New-Object System.IO.MemoryStream
  $pb.StandardOutput.BaseStream.CopyTo($jms)
  $pb.WaitForExit()
  if ($pb.ExitCode -ne 0) {
    Write-Output "生成 analyze JSON 失败"
    Write-Output $pb.StandardError.ReadToEnd()
    exit 3
  }
  $jsonUtf8 = $jms.ToArray()
  $t1 = Get-AnalyzeTokens $Src $analyzer $jsonUtf8
  $t2 = Get-AnalyzeTokens $Dst $analyzer $jsonUtf8
  if ($t1 -ne $t2) {
    Write-Output ("TOKEN_DIFF analyzer=" + $analyzer)
    Write-Output ("src_count=" + @($t1 -split "`n").Count + " dst_count=" + @($t2 -split "`n").Count)
    $analyzeDiff++
  } else {
    Write-Output ("TOKEN_OK analyzer=" + $analyzer + " count=" + @($t1 -split "`n").Count)
  }
}
Remove-Item -LiteralPath $tmpPy -Force -ErrorAction SilentlyContinue

if ($analyzeDiff -gt 0) {
  Write-Output ("分词结果不一致 count=" + $analyzeDiff)
  exit 4
}

Write-Output "IK 文件哈希与分词结果全部一致。"
exit 0
