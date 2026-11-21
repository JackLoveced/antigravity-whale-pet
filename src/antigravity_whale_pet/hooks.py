"""Antigravity lifecycle hooks integration (pure Python stdlib, <40ms execution).

Provides:
- `emit_hook_from_stdin()`: reads Antigravity hook JSON on stdin, fires a
  non-blocking UDP packet to the local desktop pet, and outputs valid contract JSON.
- `install_hooks()`, `disable_hooks()`, `remove_hooks()`, `hooks_status()`:
  safely manages the `antigravity-whale-pet` entry in `~/.gemini/config/hooks.json`.
"""

from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from typing import List, Optional

from antigravity_whale_pet.protocol import PET_HOST, PET_PORT

HOOK_KEY = "antigravity-whale-pet"
HOOKS_FILE = Path.home() / ".gemini" / "config" / "hooks.json"


def _send_udp(payload: dict) -> None:
    try:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if len(data) > 4096:
            data = data[:4096]
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.05)
        try:
            sock.sendto(data, (PET_HOST, PET_PORT))
        finally:
            sock.close()
    except Exception:
        pass


def emit_hook_from_stdin(extra_args: Optional[List[str]] = None) -> None:
    """Fast stdin->UDP hook handler invoked by Antigravity hooks.json."""
    raw = ""
    try:
        if not sys.stdin.isatty():
            raw = sys.stdin.read()
    except Exception:
        raw = ""

    event_data = {}
    if raw.strip():
        try:
            event_data = json.loads(raw)
        except Exception:
            event_data = {}

    fallback_name = extra_args[0] if extra_args else "Unknown"
    hook_event = event_data.get("hookEventName") or fallback_name

    tool_call = event_data.get("toolCall") or {}
    tool_name = tool_call.get("name", "") if isinstance(tool_call, dict) else ""
    error_msg = str(event_data.get("error") or "")[:120]
    term_reason = str(event_data.get("terminationReason") or "")
    last_input = str(event_data.get("lastUserInput") or "").strip().replace("\n", " ")[:48]
    model_name = str(event_data.get("modelName") or "")

    _send_udp(
        {
            "event": hook_event,
            "tool": tool_name,
            "error": error_msg,
            "reason": term_reason,
            "prompt": last_input,
            "model": model_name,
            "ts": time.time(),
        }
    )

    if hook_event == "Stop":
        sys.stdout.write(json.dumps({"decision": "stop"}) + "\n")
    else:
        sys.stdout.write("{}\n")
    sys.stdout.flush()


def _build_hook_spec(python_exe: Optional[str] = None) -> dict:
    py = python_exe or sys.executable
    cmd = f'"{py}" -m antigravity_whale_pet emit-hook'
    handler = {"type": "command", "command": cmd, "timeout": 5}
    return {
        "enabled": True,
        "SessionStart": [handler],
        "PreInvocation": [handler],
        "PostToolUse": [
            {
                "matcher": "*",
                "hooks": [handler],
            }
        ],
        "PostInvocation": [handler],
        "Stop": [handler],
    }


def _load_hooks() -> dict:
    if not HOOKS_FILE.exists():
        return {}
    raw = HOOKS_FILE.read_text(encoding="utf-8").strip()
    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"Unexpected JSON root in {HOOKS_FILE}")
    return data


def _save_hooks(data: dict) -> None:
    HOOKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    HOOKS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def install_hooks(python_exe: Optional[str] = None) -> Path:
    data = _load_hooks()
    data[HOOK_KEY] = _build_hook_spec(python_exe=python_exe)
    _save_hooks(data)
    return HOOKS_FILE


def disable_hooks() -> bool:
    data = _load_hooks()
    if HOOK_KEY not in data:
        return False
    data[HOOK_KEY]["enabled"] = False
    _save_hooks(data)
    return True


def remove_hooks() -> bool:
    data = _load_hooks()
    if HOOK_KEY not in data:
        return False
    del data[HOOK_KEY]
    _save_hooks(data)
    return True


def hooks_status() -> str:
    data = _load_hooks()
    entry = data.get(HOOK_KEY)
    if not entry:
        return f"NOT INSTALLED ({HOOKS_FILE})"
    state = "ENABLED" if entry.get("enabled", True) else "DISABLED"
    return f"{state} ({HOOKS_FILE})"
