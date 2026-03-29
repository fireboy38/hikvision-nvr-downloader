@echo off
setlocal enabledelayedexpansion

echo ========================================
echo   四川新数录像批量下载器 - 一键打包
echo ========================================
echo.

REM 设置工作目录
set WORK_DIR=%~dp0
cd /d "%WORK_DIR%"

REM 步骤1: 编译Java
echo [1/5] 编译Java代码...
if exist "hikvision_java\compile.bat" (
    call hikvision_java\compile.bat
    echo   Java编译完成
) else (
    echo [警告] 未找到Java编译脚本
)

REM 步骤2: 构建Python EXE
echo.
echo [2/5] 构建Python EXE (目录模式)...
cd hikvision_downloader
python -m PyInstaller --noconfirm --clean build_with_dll.spec
if errorlevel 1 (
    echo [错误] PyInstaller构建失败
    pause
    exit /b 1
)
cd ..

REM 步骤3: 创建输出目录
echo.
echo [3/5] 创建输出目录...
if exist "dist\四川新数录像批量下载器_完整版" rmdir /s /q "dist\四川新数录像批量下载器_完整版"
mkdir "dist\四川新数录像批量下载器_完整版"
mkdir "dist\四川新数录像批量下载器_完整版\_internal"
mkdir "dist\四川新数录像批量下载器_完整版\java"
mkdir "dist\四川新数录像批量下载器_完整版\java\lib"

REM 步骤4: 复制文件
echo.
echo [4/5] 复制文件...

REM 复制EXE
copy /y "hikvision_downloader\dist\四川新数录像批量下载器\四川新数录像批量下载器.exe" "dist\四川新数录像批量下载器_完整版\" >nul
echo   - 主程序EXE

REM 复制_internal
xcopy /e /y "hikvision_downloader\dist\四川新数录像批量下载器\_internal\*" "dist\四川新数录像批量下载器_完整版\_internal\" >nul 2>&1
echo   - _internal目录 (DLL和依赖)

REM 复制Java文件
xcopy /e /y "hikvision_java\bin\*" "dist\四川新数录像批量下载器_完整版\java\" >nul 2>&1
xcopy /e /y "hikvision_java\src\main\resources\lib\*" "dist\四川新数录像批量下载器_完整版\java\lib\" >nul 2>&1
echo   - Java组件

REM 复制配置文件
if exist "hikvision_java\DemoLocalCfg.json" copy /y "hikvision_java\DemoLocalCfg.json" "dist\四川新数录像批量下载器_完整版\" >nul
if exist "hikvision_java\DeviceCfg.json" copy /y "hikvision_java\DeviceCfg.json" "dist\四川新数录像批量下载器_完整版\" >nul
echo   - 配置文件

REM 步骤5: 创建安装程序
echo.
echo [5/5] 检查安装程序工具...

REM 检查Inno Setup
set ISCC=
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe
if exist "C:\Program Files (x86)\Inno Setup 5\ISCC.exe" set ISCC=C:\Program Files (x86)\Inno Setup 5\ISCC.exe

if defined ISCC (
    echo   找到Inno Setup，开始创建安装程序...
    if not exist "installer" mkdir installer
    "%ISCC%" "installer.iss"
    if errorlevel 1 (
        echo [警告] 安装程序创建失败
    ) else (
        echo   安装程序创建成功
    )
) else (
    echo [提示] 未安装Inno Setup，跳过安装程序创建
    echo   请从 https://jrsoftware.org/isinfo.php 下载安装Inno Setup
)

REM 完成
echo.
echo ========================================
echo   打包完成！
echo ========================================
echo.
echo 输出目录:
echo   绿色版: dist\四川新数录像批量下载器_完整版\
if exist "installer\*.exe" (
    echo   安装版: installer\*.exe
)
echo.
echo 绿色版使用方法:
echo   1. 进入 dist\四川新数录像批量下载器_完整版\
echo   2. 运行  四川新数录像批量下载器.exe
echo.
echo 按任意键打开输出目录...
pause >nul
explorer "dist\四川新数录像批量下载器_完整版"