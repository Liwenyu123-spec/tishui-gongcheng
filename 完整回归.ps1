<##
.SYNOPSIS
    执行第九步完整回归，并为每个子任务设置硬超时。

.DESCRIPTION
    每个检查都在独立 Python/Node 进程中运行。某个依赖或测试客户端卡住时，
    脚本会结束该子进程并继续输出明确的失败原因，不会占住当前终端。

    检查顺序：前端生产构建 → 后端编译 → pytest 单元用例 → Mock 冒烟回归
    → RAG 质量回归 → git diff --check。

    日常提交只需要跑提交前门禁（scripts\pre_commit_check.py，由
    安装提交检查.ps1 装成 git pre-commit 钩子），它跳过前端构建和 RAG 评测；
    本脚本用于发布或里程碑前的完整回归。
##>

param(
    [int]$SmokeTimeoutSeconds = 120,
    [int]$RagTimeoutSeconds = 180,
    [int]$BuildTimeoutSeconds = 120,
    [int]$UnitTimeoutSeconds = 120
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

function ConvertTo-CommandLine {
    param([string[]]$Arguments)

    # 把参数数组拼成命令行字符串，含空格或引号的参数用双引号包裹。
    # Windows PowerShell 5.1（.NET Framework）的 ProcessStartInfo 没有
    # ArgumentList 属性，只有 Arguments 字符串，因此这里统一走字符串拼装，
    # 让脚本在 PowerShell 5.1 和 7 下行为一致。
    $parts = foreach ($item in $Arguments) {
        if ($item -match '[\s"]') {
            '"' + ($item -replace '"', '\"') + '"'
        }
        else {
            $item
        }
    }
    return ($parts -join ' ')
}

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
    # 用 Arguments 字符串传参，避免 5.1 下 ArgumentList 为 $null 直接抛错。
    $startInfo.Arguments = ConvertTo-CommandLine $Arguments
    # 子进程输出统一按 UTF-8 处理：Python 在输出被重定向时默认使用系统代码页
    # （简体中文环境为 GBK），不显式指定会让 RAG 评测等中文输出在终端变成乱码。
    $startInfo.StandardOutputEncoding = [System.Text.UTF8Encoding]::new($false)
    $startInfo.StandardErrorEncoding = [System.Text.UTF8Encoding]::new($false)
    $startInfo.EnvironmentVariables['PYTHONIOENCODING'] = 'utf-8'
    $startInfo.EnvironmentVariables['PYTHONUTF8'] = '1'
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
    # 通过 cmd 调用 npm.cmd，避免 ProcessStartInfo 误选 frontend/node_modules/.bin 下的 npm shim。
    Invoke-BoundedCommand '前端生产构建' 'cmd.exe' @('/d', '/c', 'npm.cmd', 'run', 'build') $frontendDir $BuildTimeoutSeconds
    Invoke-BoundedCommand '后端编译' $pythonExe @('-m', 'compileall', '-q', 'app') $backendDir $BuildTimeoutSeconds
    # 单元用例先跑：失败信息比冒烟脚本更短，能先定位到具体断言。
    Invoke-BoundedCommand '后端单元用例' $pythonExe @('-m', 'pytest', 'tests', '-q') $backendDir $UnitTimeoutSeconds
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
