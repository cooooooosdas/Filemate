@echo off
chcp 65001 >nul
title FileMate 启动器
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\dev.ps1"
if errorlevel 1 (
    echo.
    echo 首次运行请在 PowerShell 执行：
    echo powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 -Setup
    pause
)
