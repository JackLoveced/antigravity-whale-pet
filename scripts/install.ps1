param(
    [string]$Mirror = "",
    [switch]$NoAutoStart
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VenvDir = Join-Path $RepoRoot ".venv"
$PyExe = Join-Path $VenvDir "Scripts\python.exe"
$PipExe = Join-Path $VenvDir "Scripts\pip.exe"
$AgyPetExe = Join-Path $VenvDir "Scripts\agy-pet.exe"

Write-Host "=== Antigravity x DeepSeek 鲸鱼娘桌面宠物 一键安装 ===" -ForegroundColor Cyan

if (-not (Test-Path $PyExe)) {
    Write-Host "[1/5] 正在创建 Python 虚拟环境 (.venv)..." -ForegroundColor Yellow
    python -m venv $VenvDir
} else {
    Write-Host "[1/5] 检测到已有 .venv，跳过创建。" -ForegroundColor Green
}

Write-Host "[2/5] 正在安装 antigravity-whale-pet 及其依赖 (PyQt6, PyAV, numpy)..." -ForegroundColor Yellow
& $PipExe install --upgrade pip setuptools wheel | Out-Null
& $PipExe install -e $RepoRoot

Write-Host "[3/5] 正在检查 / 下载 114 段鲸鱼娘透明动画素材 (MIT)..." -ForegroundColor Yellow
$LocalAssets = Join-Path $RepoRoot "assets"
if ($Mirror) {
    & $AgyPetExe fetch-assets --target $LocalAssets --mirror $Mirror
} else {
    & $AgyPetExe fetch-assets --target $LocalAssets
}

Write-Host "[4/5] 正在注册全局 Antigravity Hooks (~/.gemini/config/hooks.json)..." -ForegroundColor Yellow
& $AgyPetExe install-hooks

if (-not $NoAutoStart) {
    Write-Host "[5/5] 正在开启「随 Antigravity 自动启停」开机守护..." -ForegroundColor Yellow
    & $AgyPetExe enable-autostart --assets-dir $LocalAssets
} else {
    Write-Host "[5/5] 已跳过开机守护（随时可运行 agy-pet enable-autostart 开启）。" -ForegroundColor Gray
}

& $AgyPetExe status

Write-Host ""
Write-Host "安装完成！现在打开 Antigravity 时鲸鱼娘会自动出现、关闭时自动退出；也可随时双击 start_pet.vbs 手动启动~" -ForegroundColor Green
