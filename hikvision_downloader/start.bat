@echo off
chcp 65001 >nul
echo ========================================
echo   海康NVR批量录像下载工具
echo   Hikvision NVR Batch Downloader
echo ========================================
echo.

REM 检查Python路径
echo [提示] 正在查找Python...

where python >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set PYTHON_CMD=python
    goto :check_deps
)

if exist "C:\Program Files\Python312\python.exe" (
    set PYTHON_CMD="C:\Program Files\Python312\python.exe"
    goto :check_deps
)

echo [错误] 未找到Python，请先安装Python 3.8+
pause
exit /b 1

:check_deps
echo [提示] 正在检查依赖...
%PYTHON_CMD% -m pip show PyQt5 >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [提示] 正在安装依赖...
    %PYTHON_CMD% -m pip install -r requirements.txt
)

REM 启动程序
echo.
echo [提示] 启动程序...
cd /d "%~dp0"
%PYTHON_CMD% main.py

pause
