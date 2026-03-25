# 同步代码到 GitHub 的 PowerShell 脚本
# 使用方法: 右键点击此文件，选择"使用 PowerShell 运行"

$projectPath = "c:\Users\Administrator\WorkBuddy\20260323192840"
$gitPath = "C:\Program Files\Git\bin\git.exe"

Write-Host "==========================================" -ForegroundColor Green
Write-Host "   同步代码到 GitHub" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""

# 进入项目目录
Set-Location $projectPath

# 检查 Git 是否可用
if (-Not (Test-Path $gitPath)) {
    Write-Host "[ERROR] 找不到 Git。请确保 Git 已安装。" -ForegroundColor Red
    pause
    exit 1
}

# 检查是否有修改
$status = & $gitPath status --short 2>$null

if ([string]::IsNullOrWhiteSpace($status)) {
    Write-Host "[INFO] 没有检测到修改，无需同步。" -ForegroundColor Yellow
    Write-Host ""
    pause
    exit 0
}

Write-Host "[INFO] 检测到以下修改：" -ForegroundColor Cyan
Write-Host "------------------------------------------" -ForegroundColor Gray
$status | ForEach-Object { Write-Host "  $_" -ForegroundColor White }
Write-Host "------------------------------------------" -ForegroundColor Gray
Write-Host ""

# 获取提交信息
$commitMsg = Read-Host "请输入提交说明（直接回车使用默认说明'更新代码'）"
if ([string]::IsNullOrWhiteSpace($commitMsg)) {
    $commitMsg = "更新代码"
}

Write-Host ""
Write-Host "[INFO] 正在添加文件..." -ForegroundColor Cyan
& $gitPath add .
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] 添加文件失败" -ForegroundColor Red
    pause
    exit 1
}

Write-Host "[INFO] 正在提交..." -ForegroundColor Cyan
& $gitPath commit -m "$commitMsg"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] 提交失败" -ForegroundColor Red
    pause
    exit 1
}

Write-Host "[INFO] 正在推送到 GitHub..." -ForegroundColor Cyan
& $gitPath push origin main
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] 推送失败" -ForegroundColor Red
    pause
    exit 1
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "   同步成功！" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "仓库地址: https://github.com/fireboy38/hikvision-nvr-downloader" -ForegroundColor Cyan
Write-Host ""
pause