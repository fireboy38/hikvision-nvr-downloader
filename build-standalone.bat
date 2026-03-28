@echo off
setlocal enabledelayedexpansion

echo ========================================
echo   四川新数录像批量下载器 - 单文件打包
echo   (DLL嵌入exe，无需外部DLL文件)
echo ========================================
echo.

REM 检查Python
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [错误] 未找到Python，请先安装Python 3.8+
    pause
    exit /b 1
)

REM 进入工作目录
cd /d "%~dp0"
cd hikvision_downloader

REM 编译带DLL的单文件exe
echo [1/2] 开始编译（带DLL嵌入）...
python -m PyInstaller --noconfirm --clean build_with_dll.spec

if %ERRORLEVEL% NEQ 0 (
    echo [错误] 编译失败！
    pause
    exit /b 1
)

echo [2/2] 编译完成！

REM 显示结果
cd ..
echo.
echo ========================================
echo   打包完成！
echo ========================================
echo.

REM 显示文件信息
for %%f in ("hikvision_downloader\dist\四川新数录像批量下载器_完整版.exe") do (
    set size=%%~zf
    set /a sizeMB=!size! / 1048576
    echo 输出文件: %%f
    echo 文件大小: !sizeMB! MB
)

echo.
echo 特点:
echo   - 单个exe文件，无需外部DLL
echo   - 可直接复制到其他电脑运行
echo   - 首次启动会解压到临时目录（约2-3秒）
echo.

REM 打开输出目录
explorer "hikvision_downloader\dist"

echo 按任意键退出...
pause >nul
