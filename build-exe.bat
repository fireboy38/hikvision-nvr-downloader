@echo off
setlocal enabledelayedexpansion

echo ========================================
echo   四川新数录像批量下载器 - 编译脚本
echo ========================================
echo.

REM 检查Python
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [错误] 未找到Python，请先安装Python 3.8+
    pause
    exit /b 1
)

REM 安装PyInstaller
echo [1/6] 检查PyInstaller...
python -m pip show pyinstaller >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [1/6] 安装PyInstaller...
    pip install pyinstaller
)

REM 进入工作目录
cd /d "%~dp0"
cd hikvision_downloader

REM 编译exe
echo [2/6] 开始编译exe...
python -m PyInstaller --noconfirm --onefile --windowed --name "四川新数录像批量下载器" --paths "." --hidden-import PyQt5 --hidden-import PyQt5.sip --hidden-import requests --hidden-import urllib3 --hidden-import xml.etree.ElementTree --hidden-import xml.etree.cElementTree --hidden-import json --hidden-import datetime --hidden-import os --hidden-import sys --hidden-import subprocess --hidden-import threading --hidden-import time --hidden-import re --hidden-import pathlib --hidden-import typing --hidden-import dataclasses --hidden-import gui --hidden-import gui.main_window --hidden-import core --hidden-import core.downloader --hidden-import core.java_downloader --hidden-import core.nvr_api --hidden-import core.hcnetsdk --hidden-import core.channel_manager --hidden-import core.device_info --hidden-import core.hikload_downloader --hidden-import core.isapi_downloader --hidden-import core.osd_manager --hidden-import utils --hidden-import utils.logger main.py

if %ERRORLEVEL% NEQ 0 (
    echo [错误] 编译失败！
    pause
    exit /b 1
)

echo [3/6] 编译完成！

REM 创建发布目录
echo [4/6] 创建发布目录...
cd ..
if not exist "dist" mkdir dist
if not exist "dist\四川新数录像批量下载器" mkdir "dist\四川新数录像批量下载器"

REM 复制exe
echo [5/6] 复制文件...
copy /Y "hikvision_downloader\dist\四川新数录像批量下载器.exe" "dist\四川新数录像批量下载器\" >nul

REM 复制Java组件
echo [6/6] 复制Java组件...
if not exist "dist\四川新数录像批量下载器\hikvision_java" mkdir "dist\四川新数录像批量下载器\hikvision_java"
if not exist "dist\四川新数录像批量下载器\hikvision_java\bin" mkdir "dist\四川新数录像批量下载器\hikvision_java\bin"

REM 检查并复制Java相关文件
if exist "hikvision_java\bin\HCNetSDK.jar" (
    copy /Y "hikvision_java\bin\HCNetSDK.jar" "dist\四川新数录像批量下载器\hikvision_java\bin\" >nul
) else (
    echo [警告] 未找到 HCNetSDK.jar
)

if exist "hikvision_java\bin\jna.jar" (
    copy /Y "hikvision_java\bin\jna.jar" "dist\四川新数录像批量下载器\hikvision_java\bin\" >nul
) else (
    echo [警告] 未找到 jna.jar
)

if exist "hikvision_java\bin\examples.jar" (
    copy /Y "hikvision_java\bin\examples.jar" "dist\四川新数录像批量下载器\hikvision_java\bin\" >nul
) else (
    echo [警告] 未找到 examples.jar
)

REM 复制DLL文件
echo [7/8] 复制DLL文件...
set SDK_PATH=C:\Users\Administrator\Downloads\HCNetSDKV6.1.11.5_build20251204_Win64_ZH_20260320151956\CH-HCNetSDKV6.1.11.5_build20251204_Win64_ZH\库文件

REM 也检查备用路径
if not exist "%SDK_PATH%" (
    set SDK_PATH=C:\Users\Administrator\CH-HCNetSDKV6.1.6.45_build20210302_win64_20210508181836\CH-HCNetSDKV6.1.6.45_build20210302_win64\库文件
)

if not exist "%SDK_PATH%" (
    echo [错误] SDK路径不存在: %SDK_PATH%
    echo 请修改本脚本中的SDK_PATH变量
    pause
    exit /b 1
)

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
        copy /Y "%SDK_PATH%\%%f" "dist\四川新数录像批量下载器\" >nul
        echo   - %%f
    ) else (
        echo [警告] 未找到: %%f
    )
)

REM HCNetSDKCom文件夹
if exist "%SDK_PATH%\HCNetSDKCom" (
    xcopy /E /I /Y "%SDK_PATH%\HCNetSDKCom" "dist\四川新数录像批量下载器\HCNetSDKCom\" >nul
    echo   - HCNetSDKCom\* (子目录dll)
) else (
    echo [警告] 未找到 HCNetSDKCom 文件夹
)

REM 复制Java编译后的class文件
echo [8/8] 复制Java class文件...
if exist "hikvision_java\bin\com" (
    xcopy /E /I /Y "hikvision_java\bin\com" "dist\四川新数录像批量下载器\hikvision_java\bin\com\" >nul 2>&1
    echo   - Java class文件
)
if exist "hikvision_java\src\main\resources\lib" (
    xcopy /E /I /Y "hikvision_java\src\main\resources\lib" "dist\四川新数录像批量下载器\hikvision_java\lib\" >nul 2>&1
    echo   - Java lib文件
)

REM 配置文件
if exist "%SDK_PATH%\DemoLocalCfg.json" (
    copy /Y "%SDK_PATH%\DemoLocalCfg.json" "dist\四川新数录像批量下载器\" >nul
)

if exist "%SDK_PATH%\DeviceCfg.json" (
    copy /Y "%SDK_PATH%\DeviceCfg.json" "dist\四川新数录像批量下载器\" >nul
)

if exist "%SDK_PATH%\LocalSensorAdd.dat" (
    copy /Y "%SDK_PATH%\LocalSensorAdd.dat" "dist\四川新数录像批量下载器\" >nul
)

REM 复制V6.1.11.5 SDK的其他必要DLL
echo [7.5/8] 复制V6.1.11.5 SDK额外DLL...
for %%f in (
    AudioProcess.dll
    hlog.dll
    HmMerge.dll
    HXVA.dll
    libcrypto-3-x64.dll
    libmmd.dll
    libssl-3-x64.dll
    MP_Render.dll
    NPQos.dll
    YUVProcess.dll
    zlib1.dll
) do (
    if exist "%SDK_PATH%\%%f" (
        copy /Y "%SDK_PATH%\%%f" "dist\四川新数录像批量下载器\" >nul
        echo   - %%f
    )
)

echo.
echo ========================================
echo   打包完成！
echo ========================================
echo.
echo 输出目录: dist\四川新数录像批量下载器\
echo.
echo 文件清单:
echo   [主程序]
echo     - 四川新数录像批量下载器.exe
echo   [Java组件]
echo     - hikvision_java\bin\*.jar
echo   [SDK DLL]
echo     - HCNetSDK.dll
echo     - HCCore.dll
echo     - hpr.dll
echo     - PlayCtrl.dll
echo     - StreamTransClient.dll
echo     - SuperRender.dll
echo     - AudioRender.dll
echo     - GdiPlus.dll
echo     - libcrypto-1_1-x64.dll
echo     - libssl-1_1-x64.dll
echo     - msvcr100.dll
echo     - msvcr110.dll
echo     - HCNetSDKCom\*.dll (15个)
echo   [配置文件]
echo     - DemoLocalCfg.json
echo     - DeviceCfg.json
echo     - LocalSensorAdd.dat
echo.
echo 分发方式:
echo   1. 直接压缩 dist\四川新数录像批量下载器\ 目录为zip文件
echo   2. 运行 build-installer.bat 生成安装程序
echo.
echo 使用方法:
echo   解压后直接运行"四川新数录像批量下载器.exe"
echo.
echo 注意: 首次运行可能需要管理员权限
echo.
echo ========================================
echo.

REM 打开输出目录
explorer "dist\四川新数录像批量下载器"

echo 按任意键退出...
pause >nul

