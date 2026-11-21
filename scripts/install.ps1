param(
    [string]$Mirror = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VenvDir = Join-Path $RepoRoot ".venv"
$PyExe = Join-Path $VenvDir "Scripts\python.exe"
$PipExe = Join-Path $VenvDir "Scripts\pip.exe"
$AgyPetExe = Join-Path $VenvDir "Scripts\agy-pet.exe"

Write-Host "=== Antigravity x DeepSeek 鲸鱼娘桌面宠物 一键安装 ===" -ForegroundColor Cyan

if (-not (Test-Path $PyExe)) {
    Write-Host "[1/4] 正在创建 Python 虚拟环境 (.venv)..." -ForegroundColor Yellow
    python -m venv $VenvDir
} else {
    Write-Host "[1/4] 检测到已有 .venv，跳过创建。" -ForegroundColor Green
}

Write-Host "[2/4] 正在安装 antigravity-whale-pet 及其依赖 (PyQt6, PyAV, numpy)..." -ForegroundColor Yellow
& $PipExe install --upgrade pip | Out-Null
& $PipExe install -e $RepoRoot

Write-Host "[3/4] 正在检查 / 下载 114 段鲸鱼娘透明动画素材 (MIT)..." -ForegroundColor Yellow
$LocalAssets = Join-Path $RepoRoot "assets"
if ($Mirror) {
    & $AgyPetExe fetch-assets --target $LocalAssets --mirror $Mirror
} else {
    & $AgyPetExe fetch-assets --target $LocalAssets
}

Write-Host "[4/4] 正在注册全局 Antigravity Hooks (~/.gemini/config/hooks.json)..." -ForegroundColor Yellow
& $AgyPetExe install-hooks
& $AgyPetExe status

Write-Host ""
Write-Host "安装完成！现在可以双击 start_pet.vbs（无黑框）或在终端运行 .venv\Scripts\agy-pet.exe 启动鲸鱼娘~" -ForegroundColor Green
