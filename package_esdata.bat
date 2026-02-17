@echo off
chcp 65001 >nul
REM 打包 ES 数据：不修改系统策略，通过 Bypass 运行 PowerShell 脚本
powershell -ExecutionPolicy Bypass -File "%~dp0package_esdata.ps1" %*
pause
