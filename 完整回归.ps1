<##
.SYNOPSIS
    执行第九步完整回归，并为每个子任务设置硬超时。

.DESCRIPTION
    每个检查都在独立 Python/Node 进程中运行。某个依赖或测试客户端卡住时，
    脚本会结束该子进程并继续输出明确的失败原因，不会占住当前终端。
##>

param(
    [int]$SmokeTimeoutSeconds = 120,
    [int]$RagTimeoutSeconds = 180,
    [int]$BuildTimeoutSeconds = 120
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $projectRoot 'backend'
$frontendDir = Join-Path $projectRoot 'frontend'
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
$tempRoot = Join-Path $projectRoot '.test-temp'

if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "未找到虚拟环境：$pythonExe"
}
New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null

# 把子进程临时文件固定到项目的可写临时目录，避免系统沙箱临时目录权限变化。
$oldTemp = $env:TEMP
$oldTmp = $env:TMP
$oldTmpDir = $env:TMPDIR
$env:TEMP = $tempRoot
$env:TMP = $tempRoot
$env:TMPDIR = $tempRoot

function Invoke-BoundedCommand {
    param(
        [string]$Name,
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$WorkingDirectory,
        [int]$TimeoutSeconds
    )

    Write-Host "`n[$Name] 开始（超时 ${TimeoutSeconds}s）" -ForegroundColor Cyan
    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $FilePath
    $startInfo.WorkingDirectory = $WorkingDirectory
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.CreateNoWindow = $true
    foreach ($argument in $Arguments) {
        [void]$startInfo.ArgumentList.Add($argument)
    }
    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    [void]$process.Start()
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        try { $process.Kill($true) } catch { }
        throw "[$Name] 超时，已结束子进程。请查看对应测试日志或单独运行该命令。"
    }
    $stdout = $stdoutTask.GetAwaiter().GetResult()
    $stderr = $stderrTask.GetAwaiter().GetResult()
    if ($stdout) { Write-Host $stdout.TrimEnd() }
    if ($stderr) { Write-Host $stderr.TrimEnd() -ForegroundColor DarkYellow }
    if ($process.ExitCode -ne 0) {
        throw "[$Name] 退出码为 $($process.ExitCode)。"
    }
    Write-Host "[$Name] 通过" -ForegroundColor Green
}

try {
    Invoke-BoundedCommand '前端生产构建' 'npm.cmd' @('run', 'build') $frontendDir $BuildTimeoutSeconds
    Invoke-BoundedCommand '后端编译' $pythonExe @('-m', 'compileall', '-q', 'app') $backendDir $BuildTimeoutSeconds
    Invoke-BoundedCommand 'Mock 冒烟回归' $pythonExe @('-u', 'smoke_test.py') $backendDir $SmokeTimeoutSeconds
    Invoke-BoundedCommand 'RAG 质量回归' $pythonExe @('rag_eval.py', '--provider', 'hash') $backendDir $RagTimeoutSeconds
    Invoke-BoundedCommand '差异检查' 'git' @('diff', '--check') $projectRoot 30
    Write-Host "`n完整回归通过。" -ForegroundColor Green
}
finally {
    $env:TEMP = $oldTemp
    $env:TMP = $oldTmp
    $env:TMPDIR = $oldTmpDir
}
