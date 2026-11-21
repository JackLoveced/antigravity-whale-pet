"""Module entry point (`python -m antigravity_whale_pet`).

Fast-paths `emit-hook` before importing any GUI or media libraries so
Antigravity lifecycle hooks finish in <40ms with zero overhead.
"""

from __future__ import annotations

import sys


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "emit-hook":
        from antigravity_whale_pet.hooks import emit_hook_from_stdin

        emit_hook_from_stdin(sys.argv[2:])
        return

    from antigravity_whale_pet.cli import main as cli_main

    cli_main()


if __name__ == "__main__":
    main()
