@echo off
chcp 65001 >nul
set JAVA_HOME=C:\Program Files\Java\jdk-12.0.2
set PATH=%JAVA_HOME%\bin;%PATH%
set SDK_DIR=C:\Users\Administrator\WorkBuddy\20260323192840\hikvision_java\src\main\resources\lib

echo Running HikvisionDownloaderCLI...
"%JAVA_HOME%\bin\java.exe" -Djava.library.path="C:\Users\Administrator\CH-HCNetSDKV6.1.6.45_build20210302_win64_20210508181836\CH-HCNetSDKV6.1.6.45_build20210302_win64\库文件" -Dfile.encoding=UTF-8 -Dsun.jnu.encoding=UTF-8 -cp "%SDK_DIR%\jna.jar;src\main\java" com.hikvision.HikvisionDownloaderCLI %1 %2 %3 %4 %5 %6 %7 %8 %9
pause
