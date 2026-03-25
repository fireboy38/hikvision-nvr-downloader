@echo off
chcp 65001 >nul
set JAVA_HOME=C:\Program Files\Java\jdk-12.0.2
set PATH=%JAVA_HOME%\bin;%PATH%
set SDK_DIR=C:\Users\Administrator\WorkBuddy\20260323192840\hikvision_java\src\main\resources\lib

echo Cleaning old files...
if exist bin rmdir /s /q bin

echo.
echo Compiling HikvisionDownloader.java...
"%JAVA_HOME%\bin\javac.exe" -encoding UTF-8 -d bin -cp "%SDK_DIR%\jna.jar;%SDK_DIR%\examples.jar" "src\main\java\com\hikvision\HikvisionDownloader.java"
if errorlevel 1 (
    echo Compilation failed!
    pause
    exit /b 1
)

echo.
echo Running test...
echo.
"%JAVA_HOME%\bin\java.exe" -cp "src\main\resources\lib\jna.jar;src\main\resources\lib\examples.jar;bin" com.hikvision.HikvisionDownloader
pause
