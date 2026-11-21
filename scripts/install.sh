#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$REPO_ROOT/.venv"
MIRROR="${1:-}"

echo "=== Antigravity x DeepSeek 鲸鱼娘桌面宠物 一键安装 (macOS/Linux) ==="

if [ ! -x "$VENV_DIR/bin/python" ]; then
  echo "[1/5] 正在创建 Python 虚拟环境 (.venv)..."
  python3 -m venv "$VENV_DIR"
else
  echo "[1/5] 检测到已有 .venv，跳过创建。"
fi

echo "[2/5] 正在安装 antigravity-whale-pet 及其依赖..."
"$VENV_DIR/bin/pip" install --upgrade pip setuptools wheel >/dev/null
"$VENV_DIR/bin/pip" install -e "$REPO_ROOT"

echo "[3/5] 正在检查 / 下载 114 段鲸鱼娘透明动画素材 (MIT)..."
if [ -n "$MIRROR" ]; then
  "$VENV_DIR/bin/agy-pet" fetch-assets --target "$REPO_ROOT/assets" --mirror "$MIRROR"
else
  "$VENV_DIR/bin/agy-pet" fetch-assets --target "$REPO_ROOT/assets"
fi

echo "[4/5] 正在注册全局 Antigravity Hooks (~/.gemini/config/hooks.json)..."
"$VENV_DIR/bin/agy-pet" install-hooks

echo "[5/5] 正在开启「随 Antigravity 自动启停」开机守护..."
"$VENV_DIR/bin/agy-pet" enable-autostart --assets-dir "$REPO_ROOT/assets"
"$VENV_DIR/bin/agy-pet" status

echo ""
echo "安装完成！以后打开 Antigravity 时鲸鱼娘会自动启动、关闭时自动退出。"
echo "也可随时手动启动：\"$VENV_DIR/bin/agy-pet\""
