@echo off
chcp 65001 >nul
echo ========================================
echo   四川新数录像批量下载器 - 安装包制作
echo ========================================
echo.

set SRC_DIR=dist\四川新数录像批量下载器_完整版
set OUTPUT_DIR=installer
set OUTPUT_FILE=四川新数录像批量下载器-v2.0.zip

if not exist "%SRC_DIR%" (
    echo [错误] 找不到源目录: %SRC_DIR%
    echo 请先运行打包命令: python -m PyInstaller build_with_dll.spec
    pause
    exit /b 1
)

echo [1/3] 准备输出目录...
if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"

echo [2/3] 创建ZIP压缩包...
powershell -Command "Compress-Archive -Path '%SRC_DIR%\*' -DestinationPath '%OUTPUT_DIR%\%OUTPUT_FILE%' -Force"

echo [3/3] 完成!
echo.
echo ========================================
echo   安装包已创建
echo ========================================
echo.
echo 输出文件: %OUTPUT_DIR%\%OUTPUT_FILE%
echo.
echo 使用方法:
echo   1. 将ZIP文件发送给用户
echo   2. 用户解压到任意目录
echo   3. 运行 四川新数录像批量下载器.exe
echo.

:: 打开输出目录
explorer "%OUTPUT_DIR%"
