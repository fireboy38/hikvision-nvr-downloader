@echo off
cd /d "%~dp0"
chcp 65001 >nul
set "JAVA_HOME=C:\Program Files\Java\jdk-12.0.2"
set "PATH=%JAVA_HOME%\bin;%PATH%"
set "SDK_DIR=src\main\resources\lib"

echo Compiling...
"%JAVA_HOME%\bin\javac.exe" -encoding UTF-8 -d bin -cp "%SDK_DIR%\jna.jar;%SDK_DIR%\examples.jar" "src\main\java\com\hikvision\HikvisionDownloaderCLI.java"
echo Exit code: %errorlevel%
if %errorlevel% neq 0 (
    echo Compilation FAILED!
) else (
    echo OK
)
pause
