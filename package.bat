@echo off
setlocal enabledelayedexpansion

echo ========================================
echo   四川新数录像批量下载器 - 完整打包脚本
echo ========================================
echo.

REM 设置路径
set SDK_PATH=C:\Users\Administrator\CH-HCNetSDKV6.1.6.45_build20210302_win64_20210508181836\CH-HCNetSDKV6.1.6.45_build20210302_win64\库文件
set OUTPUT_DIR=%CD%\dist\四川新数录像批量下载器

REM 检查SDK路径
if not exist "%SDK_PATH%" (
    echo [错误] SDK路径不存在: %SDK_PATH%
    echo 请修改本脚本中的 SDK_PATH 变量
    pause
    exit /b 1
)

echo [1/8] 检查Python环境...
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [错误] 未找到Python
    pause
    exit /b 1
)

REM 安装PyInstaller
echo [2/8] 检查PyInstaller...
python -m pip show pyinstaller >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [2/8] 安装PyInstaller...
    pip install pyinstaller
)

REM 进入工作目录
cd /d "%~dp0"
cd hikvision_downloader

echo [3/8] 编译主程序...
pyinstaller --noconfirm --onefile --windowed --name "四川新数录像批量下载器" --paths "." --hidden-import PyQt5 --hidden-import PyQt5.sip --hidden-import requests --hidden-import urllib3 --hidden-import xml.etree.ElementTree --hidden-import xml.etree.cElementTree --hidden-import json --hidden-import datetime --hidden-import os --hidden-import sys --hidden-import subprocess --hidden-import threading --hidden-import time --hidden-import re --hidden-import pathlib --hidden-import typing --hidden-import dataclasses --hidden-import gui --hidden-import gui.main_window --hidden-import core --hidden-import core.downloader --hidden-import core.java_downloader --hidden-import core.nvr_api --hidden-import core.hcnetsdk --hidden-import core.channel_manager --hidden-import core.device_info --hidden-import core.hikload_downloader --hidden-import core.isapi_downloader --hidden-import core.osd_manager --hidden-import utils --hidden-import utils.logger main.py

if %ERRORLEVEL% NEQ 0 (
    echo [错误] 编译失败！
    pause
    exit /b 1
)

echo [4/8] 创建输出目录...
cd ..
if exist "%OUTPUT_DIR%" rmdir /s /q "%OUTPUT_DIR%"
mkdir "%OUTPUT_DIR%"

REM 复制exe
echo [5/8] 复制主程序...
copy /Y "hikvision_downloader\dist\四川新数录像批量下载器.exe" "%OUTPUT_DIR%\" >nul

REM 复制Java组件
echo [6/8] 复制Java组件...
if not exist "%OUTPUT_DIR%\hikvision_java" mkdir "%OUTPUT_DIR%\hikvision_java"
if not exist "%OUTPUT_DIR%\hikvision_java\bin" mkdir "%OUTPUT_DIR%\hikvision_java\bin"

if exist "hikvision_java\bin\HCNetSDK.jar" (
    copy /Y "hikvision_java\bin\HCNetSDK.jar" "%OUTPUT_DIR%\hikvision_java\bin\" >nul
)

if exist "hikvision_java\bin\jna.jar" (
    copy /Y "hikvision_java\bin\jna.jar" "%OUTPUT_DIR%\hikvision_java\bin\" >nul
)

if exist "hikvision_java\bin\examples.jar" (
    copy /Y "hikvision_java\bin\examples.jar" "%OUTPUT_DIR%\hikvision_java\bin\" >nul
)

if exist "hikvision_java\bin\HikvisionDownloaderCLI.class" (
    copy /Y "hikvision_java\bin\HikvisionDownloaderCLI.class" "%OUTPUT_DIR%\hikvision_java\bin\" >nul
)

echo [7/8] 复制海康SDK DLL文件...

REM 主DLL文件
for %%f in (
    HCNetSDK.dll
    HCCore.dll
    hpr.dll
    libcrypto-1_1-x64.dll
    libssl-1_1-x64.dll
    msvcr100.dll
    msvcr110.dll
    PlayCtrl.dll
    StreamTransClient.dll
    SuperRender.dll
    AudioRender.dll
    GdiPlus.dll
) do (
    if exist "%SDK_PATH%\%%f" (
        copy /Y "%SDK_PATH%\%%f" "%OUTPUT_DIR%\" >nul
        echo   - %%f
    ) else (
        echo [警告] 未找到: %%f
    )
)

REM HCNetSDKCom文件夹
if exist "%SDK_PATH%\HCNetSDKCom" (
    xcopy /E /I /Y "%SDK_PATH%\HCNetSDKCom" "%OUTPUT_DIR%\HCNetSDKCom\" >nul
    echo   - HCNetSDKCom\* (15个dll文件)
) else (
    echo [警告] 未找到 HCNetSDKCom 文件夹
)

REM 配置文件
if exist "%SDK_PATH%\DemoLocalCfg.json" (
    copy /Y "%SDK_PATH%\DemoLocalCfg.json" "%OUTPUT_DIR%\" >nul
)

if exist "%SDK_PATH%\DeviceCfg.json" (
    copy /Y "%SDK_PATH%\DeviceCfg.json" "%OUTPUT_DIR%\" >nul
)

if exist "%SDK_PATH%\LocalSensorAdd.dat" (
    copy /Y "%SDK_PATH%\LocalSensorAdd.dat" "%OUTPUT_DIR%\" >nul
)

echo [8/8] 复制说明文档...
if exist "README.md" (
    copy /Y "README.md" "%OUTPUT_DIR%\" >nul
)

if exist "hikvision_downloader\环境变量配置指南.md" (
    copy /Y "hikvision_downloader\环境变量配置指南.md" "%OUTPUT_DIR%\" >nul
)

if exist "hikvision_downloader\使用说明.txt" (
    copy /Y "hikvision_downloader\使用说明.txt" "%OUTPUT_DIR%\" >nul
)

REM 创建启动脚本
echo @echo off > "%OUTPUT_DIR%\启动程序.bat"
echo echo 正在启动 四川新数录像批量下载器... >> "%OUTPUT_DIR%\启动程序.bat"
echo start "" "四川新数录像批量下载器.exe" >> "%OUTPUT_DIR%\启动程序.bat"

echo.
echo ========================================
echo   打包完成！
echo ========================================
echo.
echo 输出目录: %OUTPUT_DIR%
echo.
echo 文件清单:
dir /b "%OUTPUT_DIR%"
echo.
echo 安装说明:
echo   1. 将此目录压缩成zip文件分发
echo   2. 用户解压后直接运行"四川新数录像批量下载器.exe"
echo   3. 或者运行"启动程序.bat"
echo.
echo 可选: 运行 installer.iss 生成安装程序
echo.
echo ========================================
echo.

REM 打开输出目录
explorer "%OUTPUT_DIR%"

echo 按任意键退出...
pause >nul
