@echo off
chcp 65001 >nul
cd /d "%~dp0"
"C:\Program Files\Java\jdk-12.0.2\bin\jar.exe" tf "src\main\resources\lib\jna.jar" | findstr /i "StdCall"
