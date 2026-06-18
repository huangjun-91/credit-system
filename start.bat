@echo off
chcp 65001 >nul
title 学分管理系统 - 安装启动

echo ============================================
echo    学分管理系统 - 安装与启动
echo ============================================
echo.

REM 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [INFO] 未检测到 Python，正在通过 Microsoft Store 安装...
    echo [INFO] 请在弹出的窗口中点击"获取"，等待安装完成
    start ms-windows-store://pdp/?productid=9NJ46SX7X90P
    echo.
    echo [!!!] 安装完成后，请关闭此窗口，重新双击启动脚本
    echo.
    pause
    exit /b
)

echo [OK] Python 已安装
python --version

REM 检查 Flask
pip show flask >nul 2>&1
if errorlevel 1 (
    echo [INFO] 正在安装 Flask...
    pip install flask
) else (
    echo [OK] Flask 已安装
)

echo.
echo ============================================
echo    正在启动系统...
echo    管理后台: http://127.0.0.1:5000
echo    管理员账号: admin / admin123
echo ============================================
echo.

python app.py

pause
