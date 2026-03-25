@echo off
cd /d C:\Users\Administrator\WorkBuddy\20260323192840\hikvision_java
"C:\Program Files\Java\jdk-12.0.2\bin\java.exe" -Djava.library.path="." -Dfile.encoding=UTF-8 -Dsun.jnu.encoding=UTF-8 -cp "src\main\resources\lib\jna.jar;src\main\resources\lib\examples.jar;bin" com.hikvision.HikvisionDownloaderCLI 10.26.223.253 8000 admin a1111111 1 "2026-03-25 10:00:00" "2026-03-25 11:05:00" "C:\Users\Administrator\Downloads\test_jyd_sdk_65min.mp4" "测试通道" > output_jyd.txt 2>&1
type output_jyd.txt
