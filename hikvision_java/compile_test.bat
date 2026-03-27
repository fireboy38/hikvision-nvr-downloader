@echo off
cd /d C:\Users\Administrator\WorkBuddy\20260323192840\hikvision_java
echo 正在编译...
"C:\Program Files\Java\jdk-12.0.2\bin\javac.exe" -encoding UTF-8 -cp "src\main\resources\lib\jna.jar;src\main\resources\lib\examples.jar" -d bin src\main\java\com\hikvision\HikvisionDownloaderCLI.java
echo 编译完成！
pause
