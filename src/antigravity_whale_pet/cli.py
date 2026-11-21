"""Unified CLI entry point (`agy-pet`) for Antigravity Whale Pet."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from antigravity_whale_pet import __version__
from antigravity_whale_pet.assets_manager import (
    count_webm_clips,
    fetch_assets,
    resolve_assets_dir,
)
from antigravity_whale_pet.hooks import (
    disable_hooks,
    emit_hook_from_stdin,
    hooks_status,
    install_hooks,
    remove_hooks,
)
from antigravity_whale_pet.lifecycle import (
    disable_autostart,
    enable_autostart,
    is_antigravity_running,
    is_autostart_enabled,
    is_watcher_running,
    run_watcher_daemon,
)


def _cmd_status(assets_dir_arg: str | None) -> None:
    assets_dir = resolve_assets_dir(assets_dir_arg)
    clip_count = count_webm_clips(assets_dir)
    brain_root = Path.home() / ".gemini" / "antigravity" / "brain"
    conv_count = (
        sum(1 for p in brain_root.iterdir() if p.is_dir())
        if brain_root.is_dir()
        else 0
    )

    print(f"antigravity-whale-pet v{__version__}")
    print(f"  Assets dir     : {assets_dir} ({clip_count} .webm clips)")
    print(f"  Hooks status   : {hooks_status()}")
    print(f"  Antigravity    : {'RUNNING' if is_antigravity_running() else 'NOT RUNNING'} ({conv_count} conversations)")
    print(f"  Auto-start     : {'ENABLED' if is_autostart_enabled() else 'DISABLED'}")
    print(f"  Watcher daemon : {'ACTIVE' if is_watcher_running() else 'STOPPED'}")


def main(argv: list[str] | None = None) -> None:
    args_list = sys.argv[1:] if argv is None else argv

    # Fast paths for zero-overhead hook & background lifecycle watcher
    if args_list and args_list[0] == "emit-hook":
        emit_hook_from_stdin(args_list[1:])
        return

    parser = argparse.ArgumentParser(
        prog="agy-pet",
        description="Antigravity × DeepSeek 鲸鱼娘（吃白饭的蓝色大肥鱼）桌面宠物",
    )
    parser.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")

    sub = parser.add_subparsers(dest="command")

    # run (default)
    p_run = sub.add_parser("run", help="启动桌面宠物（默认命令）")
    p_run.add_argument("--assets-dir", default=None, help="自定义素材目录（含 webm/ 文件夹）")
    p_run.add_argument("--scale", type=float, default=1.0, help="初始缩放比例（默认 1.0）")
    p_run.add_argument(
        "--follow-antigravity",
        action="store_true",
        help="跟随 Antigravity 生命周期：检测到 Antigravity 关闭时自动退出桌宠",
    )

    # watch (lifecycle daemon)
    p_watch = sub.add_parser(
        "watch",
        help="后台轻量守护进程：随 Antigravity 启动自动打开桌宠，随其关闭自动退出（<10MB 内存）",
    )
    p_watch.add_argument("--interval", type=float, default=2.0, help="检测间隔秒数（默认 2.0）")
    p_watch.add_argument("--assets-dir", default=None, help="自定义素材目录")
    p_watch.add_argument("--scale", type=float, default=1.0, help="桌宠初始缩放比例")

    # enable-autostart / disable-autostart
    p_auto_on = sub.add_parser(
        "enable-autostart",
        help="开启开机自动守护（系统登录后静默监听 Antigravity 启停并自动开关桌宠）",
    )
    p_auto_on.add_argument("--assets-dir", default=None, help="自定义素材目录")
    p_auto_on.add_argument("--scale", type=float, default=1.0, help="桌宠初始缩放比例")
    p_auto_on.add_argument(
        "--no-start",
        action="store_true",
        help="仅写入开机自启配置，暂不立即拉起守护进程",
    )

    sub.add_parser("disable-autostart", help="关闭开机自动守护并移除自启配置")

    # fetch-assets
    p_fetch = sub.add_parser("fetch-assets", help="自动下载 114 段开源鲸鱼娘透明动画素材 (MIT)")
    p_fetch.add_argument("--target", default=None, help="素材保存目录（默认 ~/.antigravity-whale-pet/assets）")
    p_fetch.add_argument("--mirror", default="", help="GitHub 加速镜像前缀（例如 https://ghfast.top/）")
    p_fetch.add_argument("--force", action="store_true", help="强制重新下载")

    # hooks management
    sub.add_parser("install-hooks", help="安装/更新全局 Antigravity Hooks (~/.gemini/config/hooks.json)")
    sub.add_parser("disable-hooks", help="临时禁用全局 Antigravity Hooks")
    sub.add_parser("remove-hooks", help="移除全局 Antigravity Hooks 配置")
    p_status = sub.add_parser("status", help="查看素材、Hooks、Antigravity 与自动启停守护状态")
    p_status.add_argument("--assets-dir", default=None, help="检查指定素材目录")

    # hidden internal hook handler
    sub.add_parser("emit-hook", help=argparse.SUPPRESS)

    ns = parser.parse_args(args_list)

    if ns.command in (None, "run"):
        from antigravity_whale_pet.app import main as launch_gui

        launch_gui(
            assets_dir=getattr(ns, "assets_dir", None),
            scale=getattr(ns, "scale", 1.0),
            follow_antigravity=getattr(ns, "follow_antigravity", False),
        )
    elif ns.command == "watch":
        run_watcher_daemon(
            poll_interval=max(0.8, ns.interval),
            assets_dir=ns.assets_dir,
            scale=ns.scale,
        )
    elif ns.command == "enable-autostart":
        loc = enable_autostart(
            assets_dir=ns.assets_dir,
            scale=ns.scale,
            start_now=not ns.no_start,
        )
        print(f"已开启「随 Antigravity 自动启停」开机守护：{loc}")
        if not ns.no_start:
            print("守护进程已在后台静默运行，打开/关闭 Antigravity 时鲸鱼娘将自动联动。")
    elif ns.command == "disable-autostart":
        if disable_autostart():
            print("已关闭「随 Antigravity 自动启停」开机守护。")
        else:
            print("当前未开启开机自动守护。")
    elif ns.command == "fetch-assets":
        target = Path(ns.target) if ns.target else None
        fetch_assets(target_dir=target, mirror_prefix=ns.mirror, force=ns.force)
    elif ns.command == "install-hooks":
        path = install_hooks()
        print(f"已安装全局 Antigravity Hooks: {path}")
    elif ns.command == "disable-hooks":
        if disable_hooks():
            print("已临时禁用全局 Antigravity Hooks。")
        else:
            print("未检测到已安装的 Antigravity Hooks。")
    elif ns.command == "remove-hooks":
        if remove_hooks():
            print("已移除全局 Antigravity Hooks。")
        else:
            print("未检测到已安装的 Antigravity Hooks。")
    elif ns.command == "status":
        _cmd_status(ns.assets_dir)


if __name__ == "__main__":
    main()
