# 智能同步代码到 GitHub
# 根据修改的文件类型自动生成提交说明

$projectPath = "c:\Users\Administrator\WorkBuddy\20260323192840"
$gitPath = "C:\Program Files\Git\bin\git.exe"

Set-Location $projectPath

# 检查是否有修改
$statusOutput = & $gitPath status --short 2>$null
if ([string]::IsNullOrWhiteSpace($statusOutput)) {
    exit 0  # 静默退出，没有修改
}

# 解析修改的文件
$added = @()
$modified = @()
$deleted = @()

foreach ($line in $statusOutput -split "`n") {
    $line = $line.Trim()
    if ([string]::IsNullOrWhiteSpace($line)) { continue }
    
    $status = $line.Substring(0, 2).Trim()
    $file = $line.Substring(3).Trim()
    
    switch ($status) {
        "??" { $added += $file }
        "A"  { $added += $file }
        "M"  { $modified += $file }
        "D"  { $deleted += $file }
    }
}

# 分析文件类型
$guiFiles = $modified | Where-Object { $_ -match "gui/" -or $_ -match "main_window" }
$coreFiles = $modified | Where-Object { $_ -match "core/" -or $_ -match "downloader|api" }
$docFiles = $modified | Where-Object { $_ -match "\.md$|README" }
$configFiles = $modified | Where-Object { $_ -match "\.json$|\.yaml$|\.toml$|config" }

# 智能生成提交说明
$descriptions = @()

# GUI修改
if ($guiFiles.Count -gt 0) {
    $descriptions += "优化界面"
}

# 核心逻辑修改
if ($coreFiles.Count -gt 0) {
    if ($coreFiles -match "fix|bug|修复") {
        $descriptions += "修复功能"
    } elseif ($coreFiles -match "add|new|新增") {
        $descriptions += "新增功能"
    } else {
        $descriptions += "优化功能"
    }
}

# 文档修改
if ($docFiles.Count -gt 0) {
    $descriptions += "更新文档"
}

# 配置修改
if ($configFiles.Count -gt 0) {
    $descriptions += "更新配置"
}

# 新增文件
if ($added.Count -gt 0) {
    if ($added.Count -eq 1) {
        $fileName = Split-Path $added[0] -Leaf
        $descriptions += "新增文件 $fileName"
    } else {
        $descriptions += "新增 $($added.Count) 个文件"
    }
}

# 删除文件
if ($deleted.Count -gt 0) {
    $descriptions += "删除文件"
}

# 构建最终提交说明
if ($descriptions.Count -eq 0) {
    $commitMsg = "更新代码"
} else {
    $commitMsg = $descriptions -join "，"
}

# 截断
if ($commitMsg.Length -gt 80) {
    $commitMsg = $commitMsg.Substring(0, 77) + "..."
}

# 执行同步
& $gitPath add . | Out-Null
& $gitPath commit -m "$commitMsg" | Out-Null
& $gitPath push origin main | Out-Null

Write-Host "[OK] 已同步: $commitMsg" -ForegroundColor Green