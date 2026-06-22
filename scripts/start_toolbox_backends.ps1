# Start all toolbox backend ports (skip if already listening)
$ErrorActionPreference = "SilentlyContinue"
$repo = "D:\copypan"

function Test-PortListening($port) {
    return [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}

function Start-Uvicorn($port, $workDir, $module) {
    if (Test-PortListening $port) {
        Write-Host "[skip] port $port already listening"
        return
    }
    $wd = if ($workDir) { Join-Path $repo $workDir } else { $repo }
    Write-Host "[start] port $port -> $module (cwd: $wd)"
    $env:PYTHONPATH = "$repo\back_mic\backend;$repo\back_mic\backend\kg_rag;$repo"
    Start-Process -FilePath "python" `
        -ArgumentList @("-m", "uvicorn", $module, "--host", "0.0.0.0", "--port", "$port") `
        -WorkingDirectory $wd `
        -WindowStyle Hidden
}

$services = @(
    @{ Port = 8002; Dir = "testA\translate\backend"; Module = "main:app" },
    @{ Port = 8004; Dir = "testA\zh2tw\backend"; Module = "main:app" },
    @{ Port = 8005; Dir = "test_B\zh2tw\backend"; Module = "main:app" },
    @{ Port = 8006; Dir = "testC\zh2tw\backend"; Module = "main:app" },
    @{ Port = 8007; Dir = "testA\generate_outline"; Module = "main:app" },
    @{ Port = 8008; Dir = "test_B\AI纲目制作"; Module = "main:app" },
    @{ Port = 8009; Dir = $null; Module = "testC.PanAI20.backend.main:app" },
    @{ Port = 8010; Dir = $null; Module = "testD.backend.app:app" },
    @{ Port = 8011; Dir = "testA\article-polish\backend"; Module = "main:app" },
    @{ Port = 8012; Dir = "test_B\article-polish\backend"; Module = "main:app" },
    @{ Port = 8013; Dir = "testC\runse\backend"; Module = "main:app" },
    @{ Port = 8021; Dir = "testA\bird-view\backend"; Module = "main:app" },
    @{ Port = 8022; Dir = "test_B\bird-view\backend"; Module = "main:app" },
    @{ Port = 8023; Dir = "testC\bird-view\backend"; Module = "main:app" },
    @{ Port = 8024; Dir = "testA\feast-outline\backend"; Module = "main:app" },
    @{ Port = 8025; Dir = "test_B\feast-outline\backend"; Module = "main:app" },
    @{ Port = 8026; Dir = "testC\feast-outline\backend"; Module = "main:app" },
    @{ Port = 8027; Dir = "testA\rough-outline\backend"; Module = "main:app" },
    @{ Port = 8028; Dir = "test_B\rough-outline\backend"; Module = "main:app" },
    @{ Port = 8029; Dir = $null; Module = "testC.rough_outline.backend.main:app" },
    @{ Port = 8030; Dir = "testA\ministerialize\backend"; Module = "main:app" },
    @{ Port = 8031; Dir = "test_B\ministerialize\backend"; Module = "main:app" },
    @{ Port = 8032; Dir = "testC\ministerialize\backend"; Module = "main:app" },
    @{ Port = 8042; Dir = $null; Module = "testC.qa_practice.qa_simple:app" }
)

foreach ($s in $services) {
    Start-Uvicorn -port $s.Port -workDir $s.Dir -module $s.Module
}

Start-Sleep -Seconds 8
Write-Host "`n=== Listening ports ==="
8000,8002,8004,8005,8006,8007,8008,8009,8010,8011,8012,8013,8021,8022,8023,8024,8025,8026,8027,8028,8029,8030,8031,8032,8042 | ForEach-Object {
    $p = $_
    if (Test-PortListening $p) { Write-Host "OK  $p" } else { Write-Host "FAIL $p" }
}
