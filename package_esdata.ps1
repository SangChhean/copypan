# 打包 ES 数据目录为 es_data.zip，便于上传到服务器
# 用法：在项目根目录执行 .\package_esdata.ps1
# 可选：.\package_esdata.ps1 -StopES 先停止 ES 再打包（数据更一致）

param(
    [switch]$StopES = $false   # 打包前是否先停止 Elasticsearch
)

$ErrorActionPreference = "Stop"
$ProjectRoot = "E:\copypan"
$EsDataPath  = Join-Path $ProjectRoot "es_data"
$ZipPath     = Join-Path $ProjectRoot "es_data.zip"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  打包 ES 数据 (es_data -> es_data.zip)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $EsDataPath)) {
    Write-Host "错误: 未找到目录 $EsDataPath" -ForegroundColor Red
    exit 1
}

if ($StopES) {
    Write-Host "[1/3] 停止 Elasticsearch 容器..." -ForegroundColor Yellow
    docker stop elasticsearch 2>$null
    if ($LASTEXITCODE -eq 0) { Write-Host "  已停止 elasticsearch" -ForegroundColor Green } else { Write-Host "  未运行或已停止" -ForegroundColor Gray }
    Start-Sleep -Seconds 2
} else {
    Write-Host "[1/3] 跳过停止 ES（若需一致快照可加参数 -StopES）" -ForegroundColor Gray
}

Write-Host "[2/3] 压缩 es_data -> es_data.zip ..." -ForegroundColor Yellow
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
Compress-Archive -Path $EsDataPath -DestinationPath $ZipPath -CompressionLevel Optimal
$size = (Get-Item $ZipPath).Length / 1MB
Write-Host "  已生成: $ZipPath ($([math]::Round($size, 2)) MB)" -ForegroundColor Green

if ($StopES) {
    Write-Host "[3/3] 重新启动 Elasticsearch..." -ForegroundColor Yellow
    docker start elasticsearch 2>$null
    if ($LASTEXITCODE -eq 0) { Write-Host "  已启动 elasticsearch" -ForegroundColor Green } else { Write-Host "  启动失败或未安装容器" -ForegroundColor Red }
} else {
    Write-Host "[3/3] 完成" -ForegroundColor Green
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  上传到服务器（在本地执行）：" -ForegroundColor Cyan
Write-Host "  scp $ZipPath 用户名@服务器IP:/opt/copypan/" -ForegroundColor White
Write-Host ""
Write-Host "  服务器上解压并挂载 ES 数据：" -ForegroundColor Cyan
Write-Host "  cd /opt/copypan" -ForegroundColor White
Write-Host "  docker stop elasticsearch; docker rm elasticsearch" -ForegroundColor White
Write-Host "  unzip -o es_data.zip" -ForegroundColor White
Write-Host "  docker run -d --name elasticsearch -p 9200:9200 -p 9300:9300 -e discovery.type=single-node -e ES_JAVA_OPTS=-Xms2g -Xmx2g -v /opt/copypan/es_data:/usr/share/elasticsearch/data elasticsearch:7.17.9" -ForegroundColor White
Write-Host "============================================================" -ForegroundColor Cyan
