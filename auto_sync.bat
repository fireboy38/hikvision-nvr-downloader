@echo off
chcp 65001 >nul
echo ==========================================
echo    自动同步代码到 GitHub
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
    exit /b 0
)

echo [INFO] 检测到修改，正在生成提交说明...

REM 生成提交说明
set "ADDED_FILES="
set "MODIFIED_FILES="
set "DELETED_FILES="

for /f "tokens=1,2" %%a in ('"C:\Program Files\Git\bin\git.exe" status --short') do (
    if "%%a"=="A" (
        if not defined ADDED_FILES (
            set "ADDED_FILES=%%b"
        ) else (
            set "ADDED_FILES=!ADDED_FILES!, %%b"
        )
    )
    if "%%a"=="M" (
        if not defined MODIFIED_FILES (
            set "MODIFIED_FILES=%%b"
        ) else (
            set "MODIFIED_FILES=!MODIFIED_FILES!, %%b"
        )
    )
    if "%%a"=="D" (
        if not defined DELETED_FILES (
            set "DELETED_FILES=%%b"
        ) else (
            set "DELETED_FILES=!DELETED_FILES!, %%b"
        )
    )
    if "%%a"=="??" (
        if not defined ADDED_FILES (
            set "ADDED_FILES=%%b"
        ) else (
            set "ADDED_FILES=!ADDED_FILES!, %%b"
        )
    )
)

REM 构建提交说明
set "COMMIT_MSG="
if defined ADDED_FILES (
    set "COMMIT_MSG=新增: !ADDED_FILES!"
)
if defined MODIFIED_FILES (
    if defined COMMIT_MSG (
        set "COMMIT_MSG=!COMMIT_MSG! | 修改: !MODIFIED_FILES!"
    ) else (
        set "COMMIT_MSG=修改: !MODIFIED_FILES!"
    )
)
if defined DELETED_FILES (
    if defined COMMIT_MSG (
        set "COMMIT_MSG=!COMMIT_MSG! | 删除: !DELETED_FILES!"
    ) else (
        set "COMMIT_MSG=删除: !DELETED_FILES!"
    )
)

REM 截断过长的提交说明
set "COMMIT_MSG=!COMMIT_MSG:~0,100!"
if not "!COMMIT_MSG!"=="" (
    if "!COMMIT_MSG:~-1!"=="|" set "COMMIT_MSG=!COMMIT_MSG:~0,-2!"
)

echo [INFO] 提交说明: !COMMIT_MSG!
echo.

REM 添加所有文件
echo [INFO] 正在添加文件...
"C:\Program Files\Git\bin\git.exe" add . >nul 2>&1

REM 提交
echo [INFO] 正在提交...
"C:\Program Files\Git\bin\git.exe" commit -m "!COMMIT_MSG!" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] 提交失败
    exit /b 1
)

REM 推送
echo [INFO] 正在推送到 GitHub...
"C:\Program Files\Git\bin\git.exe" push origin main >nul 2>&1
if errorlevel 1 (
    echo [ERROR] 推送失败
    exit /b 1
)

echo [OK] 同步完成！
echo.
exit /b 0