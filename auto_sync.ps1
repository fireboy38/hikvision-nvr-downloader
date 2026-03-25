# 自动同步代码到 GitHub
# 完全自动化：检测修改、生成提交说明、提交、推送

$projectPath = "c:\Users\Administrator\WorkBuddy\20260323192840"
$gitPath = "C:\Program Files\Git\bin\git.exe"

# 进入项目目录
Set-Location $projectPath

# 检查是否有修改
$statusOutput = & $gitPath status --short 2>$null
if ([string]::IsNullOrWhiteSpace($statusOutput)) {
    Write-Host "[INFO] 没有检测到修改" -ForegroundColor Gray
    exit 0
}

Write-Host "[INFO] 检测到修改，正在自动同步..." -ForegroundColor Cyan

# 解析修改的文件
$added = @()
$modified = @()
$deleted = @()

foreach ($line in $statusOutput -split "`n") {
    if ($line -match "^\?\?\s+(.+)") {
        $added += $matches[1]
    }
    elseif ($line -match "^A\s+(.+)") {
        $added += $matches[1]
    }
    elseif ($line -match "^M\s+(.+)") {
        $modified += $matches[1]
    }
    elseif ($line -match "^D\s+(.+)") {
        $deleted += $matches[1]
    }
}

# 生成提交说明
$parts = @()
if ($added.Count -gt 0) {
    $fileList = ($added | ForEach-Object { Split-Path $_ -Leaf }) -join ", "
    if ($fileList.Length -gt 30) { $fileList = $fileList.Substring(0, 30) + "..." }
    $parts += "新增: $fileList"
}
if ($modified.Count -gt 0) {
    $fileList = ($modified | ForEach-Object { Split-Path $_ -Leaf }) -join ", "
    if ($fileList.Length -gt 30) { $fileList = $fileList.Substring(0, 30) + "..." }
    $parts += "修改: $fileList"
}
if ($deleted.Count -gt 0) {
    $fileList = ($deleted | ForEach-Object { Split-Path $_ -Leaf }) -join ", "
    if ($fileList.Length -gt 30) { $fileList = $fileList.Substring(0, 30) + "..." }
    $parts += "删除: $fileList"
}

$commitMsg = $parts -join " | "
if ($commitMsg.Length -gt 100) {
    $commitMsg = $commitMsg.Substring(0, 100)
}

Write-Host "[INFO] 提交说明: $commitMsg" -ForegroundColor Gray

# 添加文件
& $gitPath add . | Out-Null

# 提交
$commitResult = & $gitPath commit -m "$commitMsg" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] 提交失败: $commitResult" -ForegroundColor Red
    exit 1
}

# 推送
& $gitPath push origin main | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] 推送失败" -ForegroundColor Red
    exit 1
}

Write-Host "[OK] 同步完成！" -ForegroundColor Green