"""Asset locator and automatic downloader for the 114 dsh-pet whale-girl animations.

Search order for runtime assets (`webm/`, `fonts/`, `sound/`, `logo.png`):
1. Explicit CLI `--assets-dir` or `AGY_PET_ASSETS_DIR` environment variable
2. Repo-local `./assets` (next to `pyproject.toml`, if running from source checkout)
3. Persistent user cache `~/.antigravity-whale-pet/assets`

If no assets are found yet, `fetch_assets()` downloads ONLY the needed MIT assets
from `PC2005-cloud/dsh-pet` (using `git sparse-checkout` if git is available, or
pure-Python zipball download fallback when git is not installed).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Optional

UPSTREAM_REPO = "https://github.com/PC2005-cloud/dsh-pet"
UPSTREAM_ZIP_URL = "https://github.com/PC2005-cloud/dsh-pet/archive/refs/heads/main.zip"
USER_ASSETS_DIR = Path.home() / ".antigravity-whale-pet" / "assets"


def _repo_local_assets_dir() -> Optional[Path]:
    # src/antigravity_whale_pet/assets_manager.py -> repo_root/assets
    candidate = Path(__file__).resolve().parents[2] / "assets"
    if (candidate / "webm").is_dir():
        return candidate
    cwd_candidate = Path.cwd() / "assets"
    if (cwd_candidate / "webm").is_dir():
        return cwd_candidate
    return None


def resolve_assets_dir(explicit_dir: Optional[str | Path] = None) -> Path:
    """Find the best existing assets directory, or return the default user cache dir."""
    if explicit_dir:
        return Path(explicit_dir).expanduser().resolve()

    env_dir = os.environ.get("AGY_PET_ASSETS_DIR", "").strip()
    if env_dir:
        return Path(env_dir).expanduser().resolve()

    local = _repo_local_assets_dir()
    if local is not None and any((local / "webm").glob("*.webm")):
        return local

    if (USER_ASSETS_DIR / "webm").is_dir() and any((USER_ASSETS_DIR / "webm").glob("*.webm")):
        return USER_ASSETS_DIR

    return USER_ASSETS_DIR


def count_webm_clips(assets_dir: Path) -> int:
    webm_dir = assets_dir / "webm"
    if not webm_dir.is_dir():
        return 0
    return sum(1 for _ in webm_dir.rglob("*.webm"))


def _copy_runtime_subset(dsh_assets_root: Path, target_dir: Path) -> int:
    """Copy only webm/, fonts/上首软糖体.ttf, sound/click-duck.wav, and logo.png."""
    target_webm = target_dir / "webm"
    target_fonts = target_dir / "fonts"
    target_sound = target_dir / "sound"
    target_webm.mkdir(parents=True, exist_ok=True)
    target_fonts.mkdir(parents=True, exist_ok=True)
    target_sound.mkdir(parents=True, exist_ok=True)

    copied = 0
    src_webm = dsh_assets_root / "webm"
    if src_webm.is_dir():
        for f in src_webm.rglob("*.webm"):
            shutil.copy2(f, target_webm / f.name)
            copied += 1

    src_fonts = dsh_assets_root / "fonts"
    if src_fonts.is_dir():
        for f in src_fonts.glob("*.ttf"):
            shutil.copy2(f, target_fonts / f.name)

    src_sound = dsh_assets_root / "sound"
    if src_sound.is_dir():
        for f in src_sound.glob("*.wav"):
            shutil.copy2(f, target_sound / f.name)

    logo = dsh_assets_root / "logo.png"
    if logo.is_file():
        shutil.copy2(logo, target_dir / "logo.png")

    return copied


def _try_git_sparse_fetch(
    target_dir: Path,
    repo_url: str,
    log: Callable[[str], None],
) -> int:
    if shutil.which("git") is None:
        return 0
    with tempfile.TemporaryDirectory(prefix="agy_pet_fetch_") as tmp:
        tmp_repo = Path(tmp) / "dsh-pet"
        log(f"使用 git sparse-checkout 精简拉取素材: {repo_url} ...")
        try:
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--depth",
                    "1",
                    "--filter=blob:none",
                    "--sparse",
                    repo_url,
                    str(tmp_repo),
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(tmp_repo),
                    "sparse-checkout",
                    "set",
                    "dsh-pet/assets/webm",
                    "dsh-pet/assets/fonts",
                    "dsh-pet/assets/sound",
                    "dsh-pet/assets/logo.png",
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            return _copy_runtime_subset(tmp_repo / "dsh-pet" / "assets", target_dir)
        except Exception as exc:
            log(f"git sparse-checkout 失败，自动切换 HTTP ZIP 下载 ({exc})")
            return 0


def _http_zip_fetch(
    target_dir: Path,
    zip_url: str,
    log: Callable[[str], None],
) -> int:
    log(f"正在下载开源素材压缩包: {zip_url} ...")
    with tempfile.TemporaryDirectory(prefix="agy_pet_zip_") as tmp:
        zip_path = Path(tmp) / "dsh-pet.zip"

        def _reporthook(blocks: int, block_size: int, total_size: int) -> None:
            if total_size > 0 and blocks % 120 == 0:
                pct = min(100.0, blocks * block_size * 100.0 / total_size)
                log(f"  下载进度: {pct:.1f}%")

        urllib.request.urlretrieve(zip_url, str(zip_path), reporthook=_reporthook)
        log("下载完成，正在解压所需动画素材…")
        extract_dir = Path(tmp) / "extracted"
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.namelist():
                if "/dsh-pet/assets/" in member and (
                    member.endswith(".webm")
                    or member.endswith(".ttf")
                    or member.endswith(".wav")
                    or member.endswith("/logo.png")
                ):
                    zf.extract(member, extract_dir)

        for candidate in extract_dir.glob("*/dsh-pet/assets"):
            return _copy_runtime_subset(candidate, target_dir)
    return 0


def fetch_assets(
    target_dir: Optional[Path] = None,
    mirror_prefix: str = "",
    force: bool = False,
    log: Callable[[str], None] = print,
) -> Path:
    """Download the 114 MIT whale-girl animations into target_dir (default: ~/.antigravity-whale-pet/assets)."""
    dest = Path(target_dir).expanduser().resolve() if target_dir else USER_ASSETS_DIR
    existing = count_webm_clips(dest)
    if existing >= 50 and not force:
        log(f"素材已就绪 ({existing} 段动画): {dest}")
        return dest

    prefix = mirror_prefix.strip()
    if prefix and not prefix.endswith("/"):
        prefix += "/"

    repo_url = f"{prefix}{UPSTREAM_REPO}.git" if prefix else f"{UPSTREAM_REPO}.git"
    zip_url = f"{prefix}{UPSTREAM_ZIP_URL}" if prefix else UPSTREAM_ZIP_URL

    count = _try_git_sparse_fetch(dest, repo_url, log)
    if count == 0:
        count = _http_zip_fetch(dest, zip_url, log)

    if count == 0:
        raise RuntimeError(
            "未能下载到鲸鱼娘动画素材，请检查网络连接或使用 `--mirror https://ghfast.top/` 重试。"
        )

    log(f"成功安装 {count} 段透明动画素材至: {dest}")
    return dest
