#requires -Version 5.1
<#
.SYNOPSIS
    安装或卸载提交前快速回归门禁（git pre-commit 钩子）。

.DESCRIPTION
    把 scripts\pre-commit-hook.sh 安装为 .git\hooks\pre-commit。
    安装后每次 git commit 会先执行 scripts\pre_commit_check.py：
    后端编译 + pytest 单元用例 + Mock 冒烟 + 差异检查。

    只改文档的提交会自动跳过代码检查；确实需要绕过时用
    git commit --no-verify 或设置环境变量 SKIP_PRECOMMIT=1。

    钩子文件不进入版本库（.git 目录本身不提交），所以换机器或重新 clone
    后需要重新执行本脚本。

.PARAMETER 卸载
    删除已安装的钩子，恢复成没有提交前检查的状态。

.EXAMPLE
    .\安装提交检查.ps1

.EXAMPLE
    .\安装提交检查.ps1 -卸载
#>
param(
    [switch]$卸载
)

$ErrorActionPreference = 'Stop'

# 脚本必须从仓库根目录执行，避免相对路径解析到别的工程。
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$gitDir = Join-Path $projectRoot '.git'
$sourceHook = Join-Path $projectRoot 'scripts\pre-commit-hook.sh'
$targetHook = Join-Path $gitDir 'hooks\pre-commit'
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
$checkScript = Join-Path $projectRoot 'scripts\pre_commit_check.py'

if (-not (Test-Path -LiteralPath $gitDir)) {
    throw "未找到 .git 目录：$gitDir。请在仓库根目录执行本脚本。"
}

$hooksDir = Join-Path $gitDir 'hooks'
if (-not (Test-Path -LiteralPath $hooksDir)) {
    New-Item -ItemType Directory -Path $hooksDir -Force | Out-Null
}

if ($卸载) {
    if (Test-Path -LiteralPath $targetHook) {
        Remove-Item -LiteralPath $targetHook -Force
        Write-Host "已卸载提交前检查：$targetHook" -ForegroundColor Green
    }
    else {
        Write-Host "当前没有安装提交前检查。" -ForegroundColor Yellow
    }
    exit 0
}

# 安装前先确认依赖齐全，否则钩子会在提交时才报错，体验很差。
if (-not (Test-Path -LiteralPath $sourceHook)) {
    throw "缺少钩子模板：$sourceHook"
}
if (-not (Test-Path -LiteralPath $checkScript)) {
    throw "缺少检查脚本：$checkScript"
}
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "未找到虚拟环境：$pythonExe。请先创建 .venv 并安装 backend\requirements.txt。"
}

# 逐字节复制，保留 shell 脚本的 LF 行尾，避免 Windows 默认换行让 sh 解析失败。
Copy-Item -LiteralPath $sourceHook -Destination $targetHook -Force
Write-Host "已安装提交前检查：$targetHook" -ForegroundColor Green
Write-Host "生效范围：后端编译、pytest 单元用例、Mock 冒烟、git diff --check" -ForegroundColor Cyan
Write-Host "临时跳过：git commit --no-verify" -ForegroundColor DarkGray
Write-Host "完整回归（含前端构建和 RAG 质量）：.\完整回归.ps1" -ForegroundColor DarkGray
