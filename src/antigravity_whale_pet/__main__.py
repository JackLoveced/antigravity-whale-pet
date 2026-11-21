"""Module entry point (`python -m antigravity_whale_pet`).

Fast-paths `emit-hook` and `watch` before importing any GUI or media libraries
so hooks run in <40ms and the background Antigravity lifecycle watcher stays <10 MB RAM.
"""

from __future__ import annotations

import sys


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "emit-hook":
        from antigravity_whale_pet.hooks import emit_hook_from_stdin

        emit_hook_from_stdin(sys.argv[2:])
        return

    if len(sys.argv) > 1 and sys.argv[1] == "watch":
        import argparse

        from antigravity_whale_pet.lifecycle import run_watcher_daemon

        p = argparse.ArgumentParser(prog="agy-pet watch")
        p.add_argument("--interval", type=float, default=2.0)
        p.add_argument("--assets-dir", default=None)
        p.add_argument("--scale", type=float, default=1.0)
        ns = p.parse_args(sys.argv[2:])
        run_watcher_daemon(
            poll_interval=max(0.8, ns.interval),
            assets_dir=ns.assets_dir,
            scale=ns.scale,
        )
        return

    from antigravity_whale_pet.cli import main as cli_main

    cli_main()


if __name__ == "__main__":
    main()
