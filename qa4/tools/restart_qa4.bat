@echo off
REM File encoding must be GBK/CP936 on Chinese Windows. UTF-8 without BOM causes flash-exit.
chcp 936 >nul
setlocal EnableExtensions EnableDelayedExpansion

REM Restart qa4 backend + frontend. Does not print .env secrets.
REM Usage: restart_qa4.bat [real or fake] [draft or stable] [log8]
REM Frontend is Vite npm run dev with HMR; hard refresh if needed, no npm run build.
set "MODE=%~1"
set "CHANNEL=%~2"
set "OPT3=%~3"
if "%MODE%"=="" set "MODE=real"
if "%CHANNEL%"=="" set "CHANNEL=draft"

REM Do not use if (...) here: pipe chars and encoding can break parsing.
if /I "%MODE%"=="real" goto :mode_ok
if /I "%MODE%"=="fake" goto :mode_ok
echo [error] arg1 must be real or fake (default real)
echo [usage] restart_qa4.bat [real or fake] [draft or stable] [log8]
pause
exit /b 1
:mode_ok
if /I "%CHANNEL%"=="draft" goto :channel_ok
if /I "%CHANNEL%"=="stable" goto :channel_ok
echo [error] arg2 must be draft or stable (default draft)
echo [usage] restart_qa4.bat [real or fake] [draft or stable] [log8]
pause
exit /b 1
:channel_ok

set "QA4_LOG_STEP8_TOKENS=0"
if /I "%OPT3%"=="log8" set "QA4_LOG_STEP8_TOKENS=1"
if /I "%MODE%"=="fake" if not defined QA4_FAKE_STREAM_DELAY_MS set "QA4_FAKE_STREAM_DELAY_MS=25"

set "QA4_ROOT=G:\copypan\qa4"
set "BACKEND=%QA4_ROOT%\backend"
set "FRONTEND=%QA4_ROOT%\frontend"
set "ENVFILE=%BACKEND%\.env"
set "PY=%BACKEND%\.venv\Scripts\python.exe"
set "LOGDIR=G:\PanAI4.0×¨ÓÃ\logs\qa4_run"
set "QA4_ENV_FILE=%ENVFILE%"
set "QA4_PROMPT_CHANNEL=%CHANNEL%"

if /I "%MODE%"=="real" (
  set "QA4_LLM_MODE=live"
  set "QA4_RETRIEVAL_MODE=live"
  set "QA4_FAKE_LLM=0"
  set "MODE_LABEL=real"
) else (
  set "QA4_LLM_MODE=fake"
  set "QA4_RETRIEVAL_MODE=fake"
  set "QA4_FAKE_LLM=1"
  set "MODE_LABEL=fake"
)

echo ========================================
echo  qa4 restart  mode=%MODE_LABEL% QA4_LLM_MODE=%QA4_LLM_MODE% QA4_RETRIEVAL_MODE=%QA4_RETRIEVAL_MODE% QA4_FAKE_LLM=%QA4_FAKE_LLM%
echo  prompt channel QA4_PROMPT_CHANNEL=%QA4_PROMPT_CHANNEL%
echo  frontend: Vite npm run dev HMR, no build needed
if /I "%QA4_LOG_STEP8_TOKENS%"=="1" (
  echo  step8 token log: ON QA4_LOG_STEP8_TOKENS=1
) else (
  echo  step8 token log: OFF add arg log8 to enable
)
echo ========================================

if /I "%MODE%"=="real" (
  echo.
  echo ****************************************
  echo *  REAL model mode - this costs money
  echo ****************************************
  echo.
)

call "%~dp0stop_qa4.bat"
if errorlevel 1 (
  echo [error] stop_qa4.bat failed, aborting.
  exit /b 1
)

if not exist "%ENVFILE%" (
  echo [env] missing file QA4_ENV_FILE:
  echo       %ENVFILE%
  echo [env] copy backend\.env.example to .env and fill values.
  exit /b 1
)
if not exist "%PY%" (
  echo [env] missing venv Python: %PY%
  exit /b 1
)

set "FILL_HIT="
for /f "usebackq delims=" %%L in (`findstr /I /C:"__FILL_ME__" "%ENVFILE%" 2^>nul`) do (
  set "raw=%%L"
  set "trim=!raw: =!"
  if not "!trim!"=="" if /I not "!trim:~0,1!"=="#" (
    for /f "tokens=1 delims==" %%A in ("%%L") do (
      echo [env] still placeholder: %%A
      set "FILL_HIT=1"
    )
  )
)
if defined FILL_HIT (
  echo [env] remove __FILL_ME__ placeholders before start. Values are not printed.
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
  echo [cost] daily ask limit QA4_DAILY_LIMIT_DEFAULT=%DAILY_LIMIT%
)

echo [docker] checking qa4-redis / qa4-es / qa4-neo4j ...
powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand CgAkAEUAcgByAG8AcgBBAGMAdABpAG8AbgBQAHIAZQBmAGUAcgBlAG4AYwBlACAAPQAgACcAQwBvAG4AdABpAG4AdQBlACcACgAkAG4AYQBtAGUAcwAgAD0AIABAACgAJwBxAGEANAAtAHIAZQBkAGkAcwAnACwAJwBxAGEANAAtAGUAcwAnACwAJwBxAGEANAAtAG4AZQBvADQAagAnACkACgAkAG4AZQBlAGQAIAA9ACAAQAAoACkACgBmAG8AcgBlAGEAYwBoACAAKAAkAG4AIABpAG4AIAAkAG4AYQBtAGUAcwApACAAewAKACAAIABkAG8AYwBrAGUAcgAgAGkAbgBzAHAAZQBjAHQAIAAkAG4AIAAxAD4AJABuAHUAbABsACAAMgA+ACQAbgB1AGwAbAAKACAAIABpAGYAIAAoACQATABBAFMAVABFAFgASQBUAEMATwBEAEUAIAAtAG4AZQAgADAAKQAgAHsACgAgACAAIAAgAFcAcgBpAHQAZQAtAEgAbwBzAHQAIAAiAFsAZABvAGMAawBlAHIAXQAgALlbaFYgACQAbgAgAA1OWFsoVwz/843Hjwj/DU4bUvpeCf8iAAoAIAAgACAAIABjAG8AbgB0AGkAbgB1AGUACgAgACAAfQAKACAAIAAkAHMAdAAgAD0AIAAoAGQAbwBjAGsAZQByACAAaQBuAHMAcABlAGMAdAAgAC0AZgAgACcAewB7AC4AUwB0AGEAdABlAC4AUwB0AGEAdAB1AHMAfQB9ACcAIAAkAG4AIAAyAD4AJABuAHUAbABsACkACgAgACAAaQBmACAAKAAkAHMAdAAgAC0AZQBxACAAJwByAHUAbgBuAGkAbgBnACcAKQAgAHsACgAgACAAIAAgAFcAcgBpAHQAZQAtAEgAbwBzAHQAIAAiAFsAZABvAGMAawBlAHIAXQAgACQAbgAgAPJdKFfQj0yIIgAKACAAIAAgACAAJABuAGUAZQBkACAAKwA9ACAAJABuAAoAIAAgACAAIABjAG8AbgB0AGkAbgB1AGUACgAgACAAfQAKACAAIABXAHIAaQB0AGUALQBIAG8AcwB0ACAAIgBbAGQAbwBjAGsAZQByAF0AIAAvVKhS8l1cUGJrhHa5W2hWIAAkAG4AIAAuAC4ALgAiAAoAIAAgAGQAbwBjAGsAZQByACAAcwB0AGEAcgB0ACAAJABuACAAMQA+ACQAbgB1AGwAbAAKACAAIAAkAG4AZQBlAGQAIAArAD0AIAAkAG4ACgB9AAoAaQBmACAAKAAtAG4AbwB0ACAAJABuAGUAZQBkAC4AQwBvAHUAbgB0ACkAIAB7AAoAIAAgAFcAcgBpAHQAZQAtAEgAbwBzAHQAIAAnAFsAZABvAGMAawBlAHIAXQAgAOBlLGcwV7lbaFbvU0l7hV8nAAoAIAAgAGUAeABpAHQAIAAwAAoAfQAKACQAZABlAGEAZABsAGkAbgBlACAAPQAgACgARwBlAHQALQBEAGEAdABlACkALgBBAGQAZABTAGUAYwBvAG4AZABzACgANgAwACkACgAkAHAAZQBuAGQAaQBuAGcAIAA9ACAAQAAoACkACgB3AGgAaQBsAGUAIAAoACgARwBlAHQALQBEAGEAdABlACkAIAAtAGwAdAAgACQAZABlAGEAZABsAGkAbgBlACkAIAB7AAoAIAAgACQAcABlAG4AZABpAG4AZwAgAD0AIABAACgAKQAKACAAIABmAG8AcgBlAGEAYwBoACAAKAAkAG4AIABpAG4AIAAkAG4AZQBlAGQAKQAgAHsACgAgACAAIAAgACQAcwB0ACAAPQAgACgAZABvAGMAawBlAHIAIABpAG4AcwBwAGUAYwB0ACAALQBmACAAJwB7AHsALgBTAHQAYQB0AGUALgBTAHQAYQB0AHUAcwB9AH0AJwAgACQAbgAgADIAPgAkAG4AdQBsAGwAKQAKACAAIAAgACAAaQBmACAAKAAkAHMAdAAgAC0AbgBlACAAJwByAHUAbgBuAGkAbgBnACcAKQAgAHsAIAAkAHAAZQBuAGQAaQBuAGcAIAArAD0AIAAkAG4AIAB9AAoAIAAgAH0ACgAgACAAaQBmACAAKAAtAG4AbwB0ACAAJABwAGUAbgBkAGkAbgBnAC4AQwBvAHUAbgB0ACkAIAB7AAoAIAAgACAAIABXAHIAaQB0AGUALQBIAG8AcwB0ACAAJwBbAGQAbwBjAGsAZQByAF0AIABAYgCXuVtoVvJdMVzqficACgAgACAAIAAgAGUAeABpAHQAIAAwAAoAIAAgAH0ACgAgACAAUwB0AGEAcgB0AC0AUwBsAGUAZQBwACAALQBTAGUAYwBvAG4AZABzACAAMgAKAH0ACgBXAHIAaQB0AGUALQBIAG8AcwB0ACAAKAAnAFsAZABvAGMAawBlAHIAXQAgAEl7hV+FjfZlCP82ADAAcwAJ/wz/zU4qZzFc6n46ACAAJwAgACsAIAAoACQAcABlAG4AZABpAG4AZwAgAC0AagBvAGkAbgAgACcALAAgACcAKQApAAoAZQB4AGkAdAAgADEACgA=
if errorlevel 1 (
  echo [docker] containers not ready in time, aborting.
  exit /b 1
)

if not exist "%LOGDIR%" mkdir "%LOGDIR%"
for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "STAMP=%%I"
set "BACKEND_LOG=%LOGDIR%\backend_%STAMP%.log"
set "FRONTEND_LOG=%LOGDIR%\frontend_%STAMP%.log"

echo [start] backend log: %BACKEND_LOG%
echo [start] frontend log: %FRONTEND_LOG%
echo [start] backend http://127.0.0.1:%BACKEND_PORT%  frontend http://127.0.0.1:%FRONTEND_PORT%

start "qa4-backend" powershell -NoExit -NoProfile -ExecutionPolicy Bypass -Command "chcp 65001 | Out-Null; $env:QA4_ENV_FILE='%ENVFILE%'; $env:QA4_LLM_MODE='%QA4_LLM_MODE%'; $env:QA4_RETRIEVAL_MODE='%QA4_RETRIEVAL_MODE%'; $env:QA4_FAKE_LLM='%QA4_FAKE_LLM%'; $env:QA4_PROMPT_CHANNEL='%QA4_PROMPT_CHANNEL%'; $env:QA4_LOG_STEP8_TOKENS='%QA4_LOG_STEP8_TOKENS%'; if ('%QA4_FAKE_STREAM_DELAY_MS%' -ne '') { $env:QA4_FAKE_STREAM_DELAY_MS='%QA4_FAKE_STREAM_DELAY_MS%' }; $env:QA4_DEV_AUTOLOGIN='1'; $env:QA4_BIND_HOST='127.0.0.1'; if ('%MODE%' -eq 'real') { Write-Host 'REAL model mode - costs money' -ForegroundColor Yellow; Write-Host 'daily ask limit QA4_DAILY_LIMIT_DEFAULT=%DAILY_LIMIT%' }; Write-Host 'local autologin ON QA4_DEV_AUTOLOGIN=1 host 127.0.0.1 only' -ForegroundColor Yellow; if ('%QA4_LOG_STEP8_TOKENS%' -eq '1') { Write-Host 'QA4_LOG_STEP8_TOKENS=1 writing to this window and backend log' -ForegroundColor Cyan }; Set-Location -LiteralPath '%BACKEND%'; Write-Host 'uvicorn main:app --host 127.0.0.1 --port %BACKEND_PORT%'; & '%PY%' -m uvicorn main:app --host 127.0.0.1 --port %BACKEND_PORT% 2>&1 | Tee-Object -FilePath '%BACKEND_LOG%'"

start "qa4-frontend" powershell -NoExit -NoProfile -ExecutionPolicy Bypass -Command "chcp 65001 | Out-Null; $env:VITE_BACKEND_URL='http://127.0.0.1:%BACKEND_PORT%'; Set-Location -LiteralPath '%FRONTEND%'; Write-Host 'Vite dev server HMR, no npm run build'; Write-Host 'npm run dev -- --port %FRONTEND_PORT%'; npm run dev -- --port %FRONTEND_PORT% --host 127.0.0.1 2>&1 | Tee-Object -FilePath '%FRONTEND_LOG%'"

echo [health] polling http://127.0.0.1:%BACKEND_PORT%/healthz up to 60s ...
set "QA4_HEALTH_URL=http://127.0.0.1:%BACKEND_PORT%/healthz"
powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand CgAkAHUAcgBsACAAPQAgACQAZQBuAHYAOgBRAEEANABfAEgARQBBAEwAVABIAF8AVQBSAEwACgAkAG8AawAgAD0AIAAkAGYAYQBsAHMAZQAKAGYAbwByACAAKAAkAGkAIAA9ACAAMAA7ACAAJABpACAALQBsAHQAIAA2ADAAOwAgACQAaQArACsAKQAgAHsACgAgACAAdAByAHkAIAB7AAoAIAAgACAAIAAkAHIAIAA9ACAASQBuAHYAbwBrAGUALQBXAGUAYgBSAGUAcQB1AGUAcwB0ACAALQBVAHMAZQBCAGEAcwBpAGMAUABhAHIAcwBpAG4AZwAgAC0AVABpAG0AZQBvAHUAdABTAGUAYwAgADIAIAAtAFUAcgBpACAAJAB1AHIAbAAKACAAIAAgACAAaQBmACAAKAAkAHIALgBTAHQAYQB0AHUAcwBDAG8AZABlACAALQBnAGUAIAAyADAAMAAgAC0AYQBuAGQAIAAkAHIALgBTAHQAYQB0AHUAcwBDAG8AZABlACAALQBsAHQAIAAzADAAMAApACAAewAgACQAbwBrACAAPQAgACQAdAByAHUAZQA7ACAAYgByAGUAYQBrACAAfQAKACAAIAB9ACAAYwBhAHQAYwBoACAAewB9AAoAIAAgAFMAdABhAHIAdAAtAFMAbABlAGUAcAAgAC0AUwBlAGMAbwBuAGQAcwAgADEACgB9AAoAaQBmACAAKAAkAG8AawApACAAewAKACAAIABXAHIAaQB0AGUALQBIAG8AcwB0ACAAJwBbAGgAZQBhAGwAdABoAF0AIAAOVO968l0xXOp+JwAKACAAIABlAHgAaQB0ACAAMAAKAH0ACgBXAHIAaQB0AGUALQBIAG8AcwB0ACAAJwBbAGgAZQBhAGwAdABoAF0AIACFjfZlKmcxXOp+JwAKAGUAeABpAHQAIAAxAAoA
if errorlevel 1 (
  echo [health] backend not ready in 60s. Check logs:
  echo   %BACKEND_LOG%
  echo   %FRONTEND_LOG%
  exit /b 1
)

echo [browser] open frontend http://127.0.0.1:%FRONTEND_PORT%/
echo [frontend] Vite HMR: save source to reload; if no [qa4] frontend build in Console, hard refresh Ctrl+F5.
echo [frontend] stream debug: localStorage.setItem('qa4_debug_stream','1') then ask; see [qa4-stream] [qa4-typewriter].
if /I "%QA4_LOG_STEP8_TOKENS%"=="1" (
  echo [log8] step8 token log file: %BACKEND_LOG%
  echo [log8] search QA4_LOG_STEP8_TOKENS in that log
)
start "" "http://127.0.0.1:%FRONTEND_PORT%/"
echo [done] start complete.
endlocal
exit /b 0
