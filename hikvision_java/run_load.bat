@echo off
chcp 65001 >nul
set JAVA_HOME=C:\Program Files\Java\jdk-12.0.2
set PATH=%JAVA_HOME%\bin;%PATH%
set SDK_DIR=C:\Users\Administrator\WorkBuddy\20260323192840\hikvision_java\src\main\resources\lib
set HCNET_SDK_PATH=C:\Users\Administrator\CH-HCNetSDKV6.1.6.45_build20210302_win64_20210508181836\CH-HCNetSDKV6.1.6.45_build20210302_win64\库文件

"%JAVA_HOME%\bin\java.exe" -Djava.library.path="%HCNET_SDK_PATH%" -cp "%SDK_DIR%\jna.jar;%SDK_DIR%\examples.jar;bin" com.hikvision.test_load
echo.
echo Exit code: %ERRORLEVEL%
pause
