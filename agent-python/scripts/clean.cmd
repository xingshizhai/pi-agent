@echo off
REM Windows 快捷入口，调用 PowerShell 清理脚本
setlocal
set "SCRIPT=%~dp0clean.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" %*
