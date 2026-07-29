@echo off
chcp 65001 >nul
title FileMate 启动器

echo ========================================
echo     FileMate - 智能文件管理工具
echo ========================================
echo.

REM 检查Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.10+
    pause
    exit /b 1
)

echo [1/3] 启动后端服务 (localhost:8000)...
start "FileMate-Backend" cmd /k "cd /d %~dp0.. && python server.py"

REM 等待后端启动
timeout /t 3 /nobreak >nul

echo [2/3] 启动前端服务 (localhost:5173)...
start "FileMate-Frontend" cmd /k "cd /d %~dp0filemate\web && npm run dev"

echo [3/3] 打开浏览器...
timeout /t 5 /nobreak >nul
start http://localhost:5173

echo.
echo ========================================
echo   FileMate 启动完成！
echo   后端: http://localhost:8000
echo   前端: http://localhost:5173
echo ========================================
echo.
echo 按任意键退出...
pause >nul