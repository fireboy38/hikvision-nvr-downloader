@echo off
setlocal enabledelayedexpansion

echo ========================================
echo   四川新数录像批量下载器 - 安装程序生成脚本
echo ========================================
echo.

REM 检查Inno Setup
where iscc >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [错误] 未找到Inno Setup编译器 (iscc.exe)
    echo.
    echo 请安装Inno Setup:
    echo   官网: https://jrsoftware.org/isinfo.php
    echo   下载: https://jrsoftware.org/download.php/is.exe
    echo.
    echo 安装后请确保iscc.exe在系统PATH中
    echo.
    pause
    exit /b 1
)

REM 检查输出目录
cd /d "%~dp0"

if not exist "dist\四川新数录像批量下载器" (
    echo [错误] 未找到发布目录: dist\四川新数录像批量下载器
    echo.
    echo 请先运行 package.bat 生成发布文件
    echo.
    pause
    exit /b 1
)

echo [1/3] 检查文件...
set FILE_COUNT=0
for %%f in (dist\四川新数录像批量下载器\*.dll) do (
    set /a FILE_COUNT+=1
)

if %FILE_COUNT% LSS 10 (
    echo [警告] DLL文件较少 (%FILE_COUNT%个)，可能缺少必要的SDK文件
    echo.
    echo 如果编译失败，请确保已运行 package.bat
    echo.
)

echo [2/3] 创建安装程序目录...
if not exist "installer" mkdir installer

echo [3/3] 编译安装程序...
iscc installer.iss

if %ERRORLEVEL% NEQ 0 (
    echo [错误] 安装程序编译失败！
    pause
    exit /b 1
)

echo.
echo ========================================
echo   安装程序生成成功！
echo ========================================
echo.
echo 文件位置: installer\四川新数录像批量下载器-安装程序.exe
echo.
echo 文件大小:
for %%f in (installer\四川新数录像批量下载器-安装程序.exe) do (
    echo   %%~zf bytes (%%~ff)
)
echo.
echo 安装说明:
echo   1. 运行 installer\四川新数录像批量下载器-安装程序.exe
echo   2. 按照向导完成安装
echo   3. 桌面会创建快捷方式
echo   4. 开始菜单有卸载程序
echo.
echo 分发方式:
echo   - 直接分发安装程序exe文件
echo   - 用户双击安装，无需手动配置
echo.
echo ========================================
echo.

REM 打开安装程序目录
explorer installer

echo 按任意键退出...
pause >nul
