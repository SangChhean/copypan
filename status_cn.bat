@echo off
setlocal EnableExtensions
title Copypan CN Status

echo ============================================================
echo Copypan CN status
echo ============================================================
echo.

echo [Docker]
where docker >nul 2>&1
if errorlevel 1 (
    echo docker not in PATH
) else (
    docker ps --filter "name=elasticsearch8" --filter "status=running" --format "  ES: {{.Names}} {{.Status}}" 2>nul
    docker ps --filter "name=redis" --filter "status=running" --format "  Redis: {{.Names}} {{.Status}}" 2>nul
    docker ps --filter "name=neo4j" --filter "status=running" --format "  Neo4j: {{.Names}} {{.Status}}" 2>nul
)
echo.

echo [Port 8014 - back_cn]
powershell -NoProfile -ExecutionPolicy Bypass -Command "$c = Get-NetTCPConnection -LocalPort 8014 -State Listen -ErrorAction SilentlyContinue; if ($c) { '  LISTEN pid=' + ($c | Select-Object -First 1).OwningProcess } else { '  not listening' }"
echo.

echo [Liveness]
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { (Invoke-RestMethod -Uri 'http://127.0.0.1:8014/api/cn/liveness' -TimeoutSec 3) | ConvertTo-Json -Compress } catch { '  unreachable: ' + $_.Exception.Message }"
echo.

echo [Readiness]
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { (Invoke-RestMethod -Uri 'http://127.0.0.1:8014/api/cn/readiness' -TimeoutSec 10) | ConvertTo-Json -Compress } catch { '  unreachable: ' + $_.Exception.Message }"
echo.

pause
