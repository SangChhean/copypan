@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion

REM 一键重启 qa4 后端 + 前端。不读取 holdout，不打印 .env 内容。
set "MODE=%~1"
set "CHANNEL=%~2"
if "%MODE%"=="" set "MODE=real"
if "%CHANNEL%"=="" set "CHANNEL=draft"

if /I not "%MODE%"=="real" if /I not "%MODE%"=="fake" (
  echo 第 1 个参数须为 real 或 fake（默认 real）。
  exit /b 1
)
if /I not "%CHANNEL%"=="draft" if /I not "%CHANNEL%"=="stable" (
  echo 第 2 个参数须为 draft 或 stable（默认 draft）。
  exit /b 1
)

set "QA4_ROOT=G:\copypan\qa4"
set "BACKEND=%QA4_ROOT%\backend"
set "FRONTEND=%QA4_ROOT%\frontend"
set "ENVFILE=%BACKEND%\.env"
set "PY=%BACKEND%\.venv\Scripts\python.exe"
set "LOGDIR=G:\PanAI4.0专用\logs\qa4_run"
set "QA4_ENV_FILE=%ENVFILE%"
set "QA4_PROMPT_CHANNEL=%CHANNEL%"

if /I "%MODE%"=="real" (
  set "QA4_LLM_MODE=live"
  set "QA4_RETRIEVAL_MODE=live"
  set "QA4_FAKE_LLM=0"
  set "MODE_LABEL=真实"
) else (
  set "QA4_LLM_MODE=fake"
  set "QA4_RETRIEVAL_MODE=fake"
  set "QA4_FAKE_LLM=1"
  set "MODE_LABEL=假"
)

echo ========================================
echo  qa4 一键启停 · 模式=%MODE_LABEL%（QA4_LLM_MODE=%QA4_LLM_MODE% / QA4_RETRIEVAL_MODE=%QA4_RETRIEVAL_MODE% / QA4_FAKE_LLM=%QA4_FAKE_LLM%）
echo  提示词通道 QA4_PROMPT_CHANNEL=%QA4_PROMPT_CHANNEL%
echo ========================================

if /I "%MODE%"=="real" (
  echo.
  echo ****************************************
  echo *  真实模型模式，会产生费用
  echo ****************************************
  echo.
)

call "%~dp0stop_qa4.bat"
if errorlevel 1 (
  echo 停止旧进程时出错，中止。
  exit /b 1
)

if not exist "%ENVFILE%" (
  echo [env] 找不到文件（QA4_ENV_FILE 应对准此路径）：
  echo       %ENVFILE%
  echo [env] 请复制 backend\.env.example 为 .env 并填写。
  exit /b 1
)
if not exist "%PY%" (
  echo [env] 找不到虚拟环境 Python：%PY%
  exit /b 1
)

set "FILL_HIT="
for /f "usebackq delims=" %%L in (`findstr /I /C:"__FILL_ME__" "%ENVFILE%" 2^>nul`) do (
  set "raw=%%L"
  set "trim=!raw: =!"
  if not "!trim!"=="" if /I not "!trim:~0,1!"=="#" (
    for /f "tokens=1 delims==" %%A in ("%%L") do (
      echo [env] 尚未填写: %%A
      set "FILL_HIT=1"
    )
  )
)
if defined FILL_HIT (
  echo [env] 请去掉上述变量的 __FILL_ME__ 占位后再启动（不打印任何值）。
  exit /b 1
)

set "BACKEND_PORT=8030"
set "DAILY_LIMIT=30"
set "FRONTEND_PORT=5174"
for /f "usebackq tokens=1,* delims==" %%A in (`findstr /I /R /C:"^[ ]*QA4_PORT=" "%ENVFILE%" 2^>nul`) do set "BACKEND_PORT=%%B"
for /f "usebackq tokens=1,* delims==" %%A in (`findstr /I /R /C:"^[ ]*QA4_DAILY_LIMIT_DEFAULT=" "%ENVFILE%" 2^>nul`) do set "DAILY_LIMIT=%%B"
if exist "%FRONTEND%\.env.development" (
  for /f "usebackq tokens=1,* delims==" %%A in (`findstr /I /R /C:"^[ ]*VITE_DEV_PORT=" "%FRONTEND%\.env.development" 2^>nul`) do set "FRONTEND_PORT=%%B"
)
set "BACKEND_PORT=%BACKEND_PORT:"=%"
set "DAILY_LIMIT=%DAILY_LIMIT:"=%"
set "FRONTEND_PORT=%FRONTEND_PORT:"=%"
for /f "tokens=* delims= " %%A in ("%BACKEND_PORT%") do set "BACKEND_PORT=%%A"
for /f "tokens=* delims= " %%A in ("%DAILY_LIMIT%") do set "DAILY_LIMIT=%%A"
for /f "tokens=* delims= " %%A in ("%FRONTEND_PORT%") do set "FRONTEND_PORT=%%A"
if "%BACKEND_PORT%"=="" set "BACKEND_PORT=8030"
if "%DAILY_LIMIT%"=="" set "DAILY_LIMIT=30"
if "%FRONTEND_PORT%"=="" set "FRONTEND_PORT=5174"

if /I "%MODE%"=="real" (
  echo [费用] 当前每日提问上限 QA4_DAILY_LIMIT_DEFAULT=%DAILY_LIMIT%
)

echo [docker] 检查 qa4-redis / qa4-es / qa4-neo4j ...
powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand CgAkAEUAcgByAG8AcgBBAGMAdABpAG8AbgBQAHIAZQBmAGUAcgBlAG4AYwBlACAAPQAgACcAQwBvAG4AdABpAG4AdQBlACcACgAkAG4AYQBtAGUAcwAgAD0AIABAACgAJwBxAGEANAAtAHIAZQBkAGkAcwAnACwAJwBxAGEANAAtAGUAcwAnACwAJwBxAGEANAAtAG4AZQBvADQAagAnACkACgAkAG4AZQBlAGQAIAA9ACAAQAAoACkACgBmAG8AcgBlAGEAYwBoACAAKAAkAG4AIABpAG4AIAAkAG4AYQBtAGUAcwApACAAewAKACAAIABkAG8AYwBrAGUAcgAgAGkAbgBzAHAAZQBjAHQAIAAkAG4AIAAxAD4AJABuAHUAbABsACAAMgA+ACQAbgB1AGwAbAAKACAAIABpAGYAIAAoACQATABBAFMAVABFAFgASQBUAEMATwBEAEUAIAAtAG4AZQAgADAAKQAgAHsACgAgACAAIAAgAFcAcgBpAHQAZQAtAEgAbwBzAHQAIAAiAFsAZABvAGMAawBlAHIAXQAgALlbaFYgACQAbgAgAA1OWFsoVwz/843Hjwj/DU4bUvpeCf8iAAoAIAAgACAAIABjAG8AbgB0AGkAbgB1AGUACgAgACAAfQAKACAAIAAkAHMAdAAgAD0AIAAoAGQAbwBjAGsAZQByACAAaQBuAHMAcABlAGMAdAAgAC0AZgAgACcAewB7AC4AUwB0AGEAdABlAC4AUwB0AGEAdAB1AHMAfQB9ACcAIAAkAG4AIAAyAD4AJABuAHUAbABsACkACgAgACAAaQBmACAAKAAkAHMAdAAgAC0AZQBxACAAJwByAHUAbgBuAGkAbgBnACcAKQAgAHsACgAgACAAIAAgAFcAcgBpAHQAZQAtAEgAbwBzAHQAIAAiAFsAZABvAGMAawBlAHIAXQAgACQAbgAgAPJdKFfQj0yIIgAKACAAIAAgACAAJABuAGUAZQBkACAAKwA9ACAAJABuAAoAIAAgACAAIABjAG8AbgB0AGkAbgB1AGUACgAgACAAfQAKACAAIABXAHIAaQB0AGUALQBIAG8AcwB0ACAAIgBbAGQAbwBjAGsAZQByAF0AIAAvVKhS8l1cUGJrhHa5W2hWIAAkAG4AIAAuAC4ALgAiAAoAIAAgAGQAbwBjAGsAZQByACAAcwB0AGEAcgB0ACAAJABuACAAMQA+ACQAbgB1AGwAbAAKACAAIAAkAG4AZQBlAGQAIAArAD0AIAAkAG4ACgB9AAoAaQBmACAAKAAtAG4AbwB0ACAAJABuAGUAZQBkAC4AQwBvAHUAbgB0ACkAIAB7AAoAIAAgAFcAcgBpAHQAZQAtAEgAbwBzAHQAIAAnAFsAZABvAGMAawBlAHIAXQAgAOBlLGcwV7lbaFbvU0l7hV8nAAoAIAAgAGUAeABpAHQAIAAwAAoAfQAKACQAZABlAGEAZABsAGkAbgBlACAAPQAgACgARwBlAHQALQBEAGEAdABlACkALgBBAGQAZABTAGUAYwBvAG4AZABzACgANgAwACkACgAkAHAAZQBuAGQAaQBuAGcAIAA9ACAAQAAoACkACgB3AGgAaQBsAGUAIAAoACgARwBlAHQALQBEAGEAdABlACkAIAAtAGwAdAAgACQAZABlAGEAZABsAGkAbgBlACkAIAB7AAoAIAAgACQAcABlAG4AZABpAG4AZwAgAD0AIABAACgAKQAKACAAIABmAG8AcgBlAGEAYwBoACAAKAAkAG4AIABpAG4AIAAkAG4AZQBlAGQAKQAgAHsACgAgACAAIAAgACQAcwB0ACAAPQAgACgAZABvAGMAawBlAHIAIABpAG4AcwBwAGUAYwB0ACAALQBmACAAJwB7AHsALgBTAHQAYQB0AGUALgBTAHQAYQB0AHUAcwB9AH0AJwAgACQAbgAgADIAPgAkAG4AdQBsAGwAKQAKACAAIAAgACAAaQBmACAAKAAkAHMAdAAgAC0AbgBlACAAJwByAHUAbgBuAGkAbgBnACcAKQAgAHsAIAAkAHAAZQBuAGQAaQBuAGcAIAArAD0AIAAkAG4AIAB9AAoAIAAgAH0ACgAgACAAaQBmACAAKAAtAG4AbwB0ACAAJABwAGUAbgBkAGkAbgBnAC4AQwBvAHUAbgB0ACkAIAB7AAoAIAAgACAAIABXAHIAaQB0AGUALQBIAG8AcwB0ACAAJwBbAGQAbwBjAGsAZQByAF0AIABAYgCXuVtoVvJdMVzqficACgAgACAAIAAgAGUAeABpAHQAIAAwAAoAIAAgAH0ACgAgACAAUwB0AGEAcgB0AC0AUwBsAGUAZQBwACAALQBTAGUAYwBvAG4AZABzACAAMgAKAH0ACgBXAHIAaQB0AGUALQBIAG8AcwB0ACAAKAAnAFsAZABvAGMAawBlAHIAXQAgAEl7hV+FjfZlCP82ADAAcwAJ/wz/zU4qZzFc6n46ACAAJwAgACsAIAAoACQAcABlAG4AZABpAG4AZwAgAC0AagBvAGkAbgAgACcALAAgACcAKQApAAoAZQB4AGkAdAAgADEACgA=
if errorlevel 1 (
  echo [docker] 容器未在时限内就绪，中止启动。
  exit /b 1
)

if not exist "%LOGDIR%" mkdir "%LOGDIR%"
for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "STAMP=%%I"
set "BACKEND_LOG=%LOGDIR%\backend_%STAMP%.log"
set "FRONTEND_LOG=%LOGDIR%\frontend_%STAMP%.log"

echo [start] 后端日志: %BACKEND_LOG%
echo [start] 前端日志: %FRONTEND_LOG%
echo [start] 后端 http://127.0.0.1:%BACKEND_PORT%  前端 http://127.0.0.1:%FRONTEND_PORT%

start "qa4-backend" powershell -NoExit -NoProfile -ExecutionPolicy Bypass -Command "chcp 65001 | Out-Null; $env:QA4_ENV_FILE='%ENVFILE%'; $env:QA4_LLM_MODE='%QA4_LLM_MODE%'; $env:QA4_RETRIEVAL_MODE='%QA4_RETRIEVAL_MODE%'; $env:QA4_FAKE_LLM='%QA4_FAKE_LLM%'; $env:QA4_PROMPT_CHANNEL='%QA4_PROMPT_CHANNEL%'; $env:QA4_DEV_AUTOLOGIN='1'; $env:QA4_BIND_HOST='127.0.0.1'; if ('%MODE%' -eq 'real') { Write-Host '真实模型模式，会产生费用' -ForegroundColor Yellow; Write-Host '每日提问上限 QA4_DAILY_LIMIT_DEFAULT=%DAILY_LIMIT%' }; Write-Host '本机免登录已开启（QA4_DEV_AUTOLOGIN=1，仅 127.0.0.1）' -ForegroundColor Yellow; Set-Location -LiteralPath '%BACKEND%'; Write-Host 'uvicorn main:app --host 127.0.0.1 --port %BACKEND_PORT%'; & '%PY%' -m uvicorn main:app --host 127.0.0.1 --port %BACKEND_PORT% 2>&1 | Tee-Object -FilePath '%BACKEND_LOG%'"

start "qa4-frontend" powershell -NoExit -NoProfile -ExecutionPolicy Bypass -Command "chcp 65001 | Out-Null; $env:VITE_BACKEND_URL='http://127.0.0.1:%BACKEND_PORT%'; Set-Location -LiteralPath '%FRONTEND%'; Write-Host 'npm run dev -- --port %FRONTEND_PORT%'; npm run dev -- --port %FRONTEND_PORT% --host 127.0.0.1 2>&1 | Tee-Object -FilePath '%FRONTEND_LOG%'"

echo [health] 轮询 http://127.0.0.1:%BACKEND_PORT%/healthz （最多 60 秒）...
set "QA4_HEALTH_URL=http://127.0.0.1:%BACKEND_PORT%/healthz"
powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand CgAkAHUAcgBsACAAPQAgACQAZQBuAHYAOgBRAEEANABfAEgARQBBAEwAVABIAF8AVQBSAEwACgAkAG8AawAgAD0AIAAkAGYAYQBsAHMAZQAKAGYAbwByACAAKAAkAGkAIAA9ACAAMAA7ACAAJABpACAALQBsAHQAIAA2ADAAOwAgACQAaQArACsAKQAgAHsACgAgACAAdAByAHkAIAB7AAoAIAAgACAAIAAkAHIAIAA9ACAASQBuAHYAbwBrAGUALQBXAGUAYgBSAGUAcQB1AGUAcwB0ACAALQBVAHMAZQBCAGEAcwBpAGMAUABhAHIAcwBpAG4AZwAgAC0AVABpAG0AZQBvAHUAdABTAGUAYwAgADIAIAAtAFUAcgBpACAAJAB1AHIAbAAKACAAIAAgACAAaQBmACAAKAAkAHIALgBTAHQAYQB0AHUAcwBDAG8AZABlACAALQBnAGUAIAAyADAAMAAgAC0AYQBuAGQAIAAkAHIALgBTAHQAYQB0AHUAcwBDAG8AZABlACAALQBsAHQAIAAzADAAMAApACAAewAgACQAbwBrACAAPQAgACQAdAByAHUAZQA7ACAAYgByAGUAYQBrACAAfQAKACAAIAB9ACAAYwBhAHQAYwBoACAAewB9AAoAIAAgAFMAdABhAHIAdAAtAFMAbABlAGUAcAAgAC0AUwBlAGMAbwBuAGQAcwAgADEACgB9AAoAaQBmACAAKAAkAG8AawApACAAewAKACAAIABXAHIAaQB0AGUALQBIAG8AcwB0ACAAJwBbAGgAZQBhAGwAdABoAF0AIAAOVO968l0xXOp+JwAKACAAIABlAHgAaQB0ACAAMAAKAH0ACgBXAHIAaQB0AGUALQBIAG8AcwB0ACAAJwBbAGgAZQBhAGwAdABoAF0AIACFjfZlKmcxXOp+JwAKAGUAeABpAHQAIAAxAAoA
if errorlevel 1 (
  echo [health] 后端未在 60 秒内就绪。请查看日志：
  echo   %BACKEND_LOG%
  echo   %FRONTEND_LOG%
  exit /b 1
)

echo [browser] 打开前端 http://127.0.0.1:%FRONTEND_PORT%/
start "" "http://127.0.0.1:%FRONTEND_PORT%/"
echo [done] 启动完成。
endlocal
exit /b 0
