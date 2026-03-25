@echo off
chcp 65001 >nul
echo ==========================================
echo    同步代码到 GitHub
echo ==========================================
echo.

cd /d "c:\Users\Administrator\WorkBuddy\20260323192840"

REM 检查是否有修改
"C:\Program Files\Git\bin\git.exe" status --short > %TEMP%\git_status.txt
set /p GIT_STATUS=<%TEMP%\git_status.txt
del %TEMP%\git_status.txt

if "%GIT_STATUS%"=="" (
    echo [INFO] 没有检测到修改
    echo.
    pause
    exit /b 0
)

echo [INFO] 检测到以下修改：
echo ------------------------------------------
"C:\Program Files\Git\bin\git.exe" status --short
echo ------------------------------------------
echo.

REM 获取提交信息
set /p COMMIT_MSG=请输入提交说明（直接回车使用默认说明"更新代码"）：
if "%COMMIT_MSG%"=="" set COMMIT_MSG=更新代码

echo.
echo [INFO] 正在添加文件...
"C:\Program Files\Git\bin\git.exe" add .

echo [INFO] 正在提交...
"C:\Program Files\Git\bin\git.exe" commit -m "%COMMIT_MSG%"
if errorlevel 1 (
    echo [ERROR] 提交失败
    pause
    exit /b 1
)

echo [INFO] 正在推送到 GitHub...
"C:\Program Files\Git\bin\git.exe" push origin main
if errorlevel 1 (
    echo [ERROR] 推送失败
    pause
    exit /b 1
)

echo.
echo ==========================================
echo    同步成功！
echo ==========================================
echo.
echo 仓库地址: https://github.com/fireboy38/hikvision-nvr-downloader
echo.
pause