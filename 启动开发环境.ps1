<#
项目开发环境一键启动脚本。

脚本会打开两个终端窗口：
1. 后端 FastAPI：127.0.0.1:8000
2. 前端 Vite：127.0.0.1:5173

关闭对应终端窗口即可停止对应服务。
#>

param(
    # 只检查目录和虚拟环境，不打开服务窗口，便于排查启动前置条件。
    [switch]$CheckOnly
)

# 遇到目录或虚拟环境缺失时立即停止，避免打开一个看似成功但无法访问的页面。
$ErrorActionPreference = "Stop"

# 以脚本文件所在目录作为项目根目录，避免从其他目录双击时路径失效。
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $projectRoot "backend"
$frontendDir = Join-Path $projectRoot "frontend"
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"

# 启动前检查项目虚拟环境和前端目录。
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "未找到项目虚拟环境：$pythonExe"
}
if (-not (Test-Path -LiteralPath (Join-Path $frontendDir "package.json"))) {
    throw "未找到前端目录：$frontendDir"
}

if ($CheckOnly) {
    Write-Host "启动脚本路径检查通过。" -ForegroundColor Green
    exit 0
}

# 使用 cmd /k 保留服务日志窗口，便于查看启动错误和按 Ctrl+C 停止服务。
$backendCommand = 'cd /d "' + $backendDir + '" && "' + $pythonExe + '" -m app'
$frontendCommand = 'cd /d "' + $frontendDir + '" && npm.cmd run dev -- --host 127.0.0.1'

# 后端和前端分别使用独立窗口启动，互不阻塞。
Start-Process -FilePath "cmd.exe" -ArgumentList @("/k", $backendCommand) -WindowStyle Normal | Out-Null
Start-Process -FilePath "cmd.exe" -ArgumentList @("/k", $frontendCommand) -WindowStyle Normal | Out-Null

Write-Host "后端启动窗口已打开： http://127.0.0.1:8000/docs" -ForegroundColor Green
Write-Host "前端启动窗口已打开： http://127.0.0.1:5173/login" -ForegroundColor Green
Write-Host "请等待前端窗口显示 Local 地址后再打开浏览器。" -ForegroundColor Yellow
