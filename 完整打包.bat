@echo off
chcp 65001 >nul
echo ================================================
echo  四川新数录像批量下载器 - 完整打包
echo ================================================
echo.

REM 检查Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到Python，请先安装Python 3.11+
    pause
    exit /b 1
)

REM 检查Java
java -version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到Java，请先安装JDK
    pause
    exit /b 1
)

REM 设置SDK路径（V6.1.11.5）
set SDK_PATH=C:\Users\Administrator\Downloads\HCNetSDKV6.1.11.5_build20251204_Win64_ZH_20260320151956\CH-HCNetSDKV6.1.11.5_build20251204_Win64_ZH\库文件
if not exist "%SDK_PATH%" (
    echo [错误] SDK路径不存在: %SDK_PATH%
    echo 请修改本脚本中的SDK_PATH变量
    pause
    exit /b 1
)

REM 创建输出目录
set OUTPUT_DIR=dist\四川新数录像批量下载器_完整版
if not exist "dist" mkdir dist
if exist "%OUTPUT_DIR%" rmdir /s /q "%OUTPUT_DIR%"
mkdir "%OUTPUT_DIR%"

echo.
echo [1/5] 编译Java代码...
echo.
cd hikvision_java
javac -encoding UTF-8 -d bin -cp "src\main\resources\lib\jna.jar;src\main\resources\lib\examples.jar" src\main\java\com\hikvision\HikvisionDownloaderCLI.java 2>nul
if errorlevel 1 (
    echo [警告] Java编译可能有问题，继续...
)
cd ..

echo.
echo [2/5] 构建Python EXE (目录模式)...
echo.
cd hikvision_downloader
python -m PyInstaller --noconfirm --clean build_with_dll.spec
cd ..

if not exist "hikvision_downloader\dist\四川新数录像批量下载器" (
    echo [错误] PyInstaller构建失败
    pause
    exit /b 1
)

echo.
echo [3/5] 复制程序文件到输出目录...
echo.
xcopy /e /y "hikvision_downloader\dist\四川新数录像批量下载器\*" "%OUTPUT_DIR%\" >nul

echo.
echo [4/5] 复制必要文件...
echo.

REM 复制Java相关文件
if not exist "%OUTPUT_DIR%\java" mkdir "%OUTPUT_DIR%\java"
xcopy /e /y "hikvision_java\bin\*" "%OUTPUT_DIR%\java\" >nul 2>&1
if exist "hikvision_java\src\main\resources\lib" (
    xcopy /e /y "hikvision_java\src\main\resources\lib\*" "%OUTPUT_DIR%\java\lib\" >nul 2>&1
)

REM 复制配置文件
if exist "hikvision_java\DemoLocalCfg.json" copy /y "hikvision_java\DemoLocalCfg.json" "%OUTPUT_DIR%\" >nul
if exist "hikvision_java\DeviceCfg.json" copy /y "hikvision_java\DeviceCfg.json" "%OUTPUT_DIR%\" >nul

echo.
echo [5/5] 复制SDK DLL文件...
echo.

REM 复制主DLL
for %%f in (HCNetSDK.dll HCCore.dll hpr.dll PlayCtrl.dll SuperRender.dll AudioRender.dll GdiPlus.dll AudioProcess.dll hlog.dll HmMerge.dll HXVA.dll libcrypto-3-x64.dll libmmd.dll libssl-3-x64.dll MP_Render.dll NPQos.dll OpenAL32.dll YUVProcess.dll zlib1.dll) do (
    if exist "%SDK_PATH%\%%f" (
        copy /y "%SDK_PATH%\%%f" "%OUTPUT_DIR%\" >nul
        echo  复制: %%f
    )
)

REM 复制HCNetSDKCom子目录
if not exist "%OUTPUT_DIR%\HCNetSDKCom" mkdir "%OUTPUT_DIR%\HCNetSDKCom"
if exist "%SDK_PATH%\HCNetSDKCom" (
    for %%f in ("%SDK_PATH%\HCNetSDKCom\*.dll") do (
        copy /y "%%f" "%OUTPUT_DIR%\HCNetSDKCom\" >nul
        echo  复制: %%~nxf
    )
)

echo.
echo ================================================
echo  打包完成！
echo ================================================
echo.
echo 输出目录: %OUTPUT_DIR%
echo.

REM 计算目录大小
for /f "tokens=3" %%a in ('dir "%OUTPUT_DIR%" /s /-c ^| find "bytes"') do set SIZE=%%a
echo 打包大小: approximately !SIZE:~0,-3! KB

echo.
echo 正在创建安装程序...
echo.

REM 检查Inno Setup
set ISCC_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe
if not exist "%ISCC_PATH%" (
    set ISCC_PATH=C:\Program Files (x86)\Inno Setup 5\ISCC.exe
)
if not exist "%ISCC_PATH%" (
    echo [警告] 未找到Inno Setup，跳过安装程序创建
    echo 请从 https://jrsoftware.org/isinfo.php 下载安装Inno Setup
    goto :end
)

REM 创建输出目录
if not exist "installer" mkdir installer

REM 复制installer.iss到临时位置并更新路径
copy /y "installer.iss" "temp_installer.iss" >nul

"%ISCC_PATH%" "temp_installer.iss"
if errorlevel 1 (
    echo [错误] Inno Setup编译失败
    del temp_installer.iss 2>nul
    pause
    exit /b 1
)

del temp_installer.iss 2>nul

if exist "installer\四川新数录像批量下载器-安装程序-v2.0.exe" (
    echo.
    echo ================================================
    echo  安装程序创建成功！
    echo ================================================
    echo.
    echo 安装程序: installer\四川新数录像批量下载器-安装程序-v2.0.exe
)

:end
echo.
pause