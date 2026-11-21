"""Real-time Antigravity activity & token watcher via live transcript.jsonl tailing."""

from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Dict, Optional, Set

from PyQt6.QtCore import QObject, pyqtSignal


_USER_REQ_RE = re.compile(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", re.DOTALL)
_EXIT_CODE_RE = re.compile(r"Command exited with code\s+(-?\d+)")


def _extract_user_prompt(content: str) -> str:
    m = _USER_REQ_RE.search(content or "")
    text = m.group(1) if m else (content or "")
    text = " ".join(text.strip().split())
    return text[:42]


def _extract_tool_detail(tool_call: dict) -> str:
    name = str(tool_call.get("name") or "")
    args = tool_call.get("args") or {}
    if not isinstance(args, dict):
        return ""
    if name in ("read_file", "edit_file", "write_file", "view_file"):
        path = str(args.get("Path") or args.get("path") or "")
        return os.path.basename(path) if path else ""
    if name == "run_command":
        summary = str(args.get("toolSummary") or "").strip()
        if summary:
            return summary[:28]
        cmd = str(args.get("CommandLine") or "").strip()
        return cmd[:24]
    if name == "invoke_subagent":
        return str(args.get("Role") or args.get("TypeName") or "")[:24]
    if name == "search_web":
        return str(args.get("query") or "")[:24]
    return ""


def _extract_tokens(obj: dict) -> int:
    total = 0
    for key in ("input_tokens", "output_tokens", "cache_read_tokens"):
        val = obj.get(key)
        if isinstance(val, (int, float)) and val > 0:
            total += int(val)
    return total


class AntigravityLiveWatcher(QObject):
    """Watches Antigravity brain transcripts in real time and emits state events."""

    activity_detected = pyqtSignal(dict)
    watcher_status = pyqtSignal(str)

    def __init__(self, poll_interval: float = 0.20) -> None:
        super().__init__()
        self._poll_interval = poll_interval
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._brain_roots = [
            Path.home() / ".gemini" / "antigravity" / "brain",
            Path.home() / ".gemini" / "antigravity-ide" / "brain",
            Path.home() / ".gemini" / "antigravity-cli" / "brain",
        ]
        self._offsets: Dict[Path, int] = {}
        self._buffers: Dict[Path, str] = {}
        self._primary_convs: Set[Path] = set()
        self._known_files_scan_ts: float = 0.0
        self._tracked_files: Set[Path] = set()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _discover_transcripts(self) -> Set[Path]:
        found: Set[Path] = set()
        for root in self._brain_roots:
            if not root.exists():
                continue
            try:
                for entry in root.iterdir():
                    if not entry.is_dir():
                        continue
                    tfile = entry / ".system_generated" / "logs" / "transcript.jsonl"
                    if tfile.exists():
                        found.add(tfile)
            except OSError:
                continue
        return found

    def _is_primary_conversation(self, path: Path) -> bool:
        if path in self._primary_convs:
            return True
        try:
            with path.open("rb") as f:
                head = f.read(16384).decode("utf-8", errors="ignore")
            if '"USER_EXPLICIT"' in head:
                self._primary_convs.add(path)
                return True
        except OSError:
            pass
        return False

    def _seed_initial_offsets(self) -> None:
        files = self._discover_transcripts()
        self._tracked_files = files
        now = time.time()
        freshest_file: Optional[Path] = None
        freshest_mtime: float = 0.0

        for path in files:
            try:
                st = path.stat()
                self._offsets[path] = st.st_size
                self._buffers[path] = ""
                if self._is_primary_conversation(path) and st.st_mtime > freshest_mtime:
                    freshest_mtime = st.st_mtime
                    freshest_file = path
            except OSError:
                continue

        self.watcher_status.emit(f"实时会话监控已连接（监听 {len(files)} 个 Antigravity 会话）")

        if freshest_file is not None and (now - freshest_mtime) < 25.0:
            self._emit_tail_snapshot(freshest_file)

    def _emit_tail_snapshot(self, path: Path) -> None:
        try:
            with path.open("rb") as f:
                f.seek(max(0, path.stat().st_size - 16384))
                tail = f.read().decode("utf-8", errors="ignore")
            lines = [ln for ln in tail.splitlines() if ln.strip()]
            for line in reversed(lines[-5:]):
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if obj.get("type") in ("USER_INPUT", "PLANNER_RESPONSE", "GENERIC"):
                    if obj.get("type") == "PLANNER_RESPONSE" and not obj.get("tool_calls"):
                        return
                    self._process_step(path, obj, is_primary=True)
                    return
        except OSError:
            pass

    def _run(self) -> None:
        self._seed_initial_offsets()
        self._known_files_scan_ts = time.time()

        while not self._stop.is_set():
            now = time.time()
            if now - self._known_files_scan_ts >= 1.2:
                self._known_files_scan_ts = now
                current = self._discover_transcripts()
                for new_path in current - self._tracked_files:
                    self._offsets[new_path] = 0
                    self._buffers[new_path] = ""
                self._tracked_files = current

            for path in list(self._tracked_files):
                try:
                    size = path.stat().st_size
                except OSError:
                    continue

                prev = self._offsets.get(path, 0)
                if size < prev:
                    prev = 0
                    self._buffers[path] = ""

                if size > prev:
                    self._read_new_lines(path, prev, size)

            self._stop.wait(self._poll_interval)

    def _read_new_lines(self, path: Path, start: int, end: int) -> None:
        try:
            with path.open("rb") as f:
                f.seek(start)
                chunk = f.read(end - start)
        except OSError:
            return

        self._offsets[path] = start + len(chunk)
        text = self._buffers.get(path, "") + chunk.decode("utf-8", errors="replace")
        lines = text.split("\n")
        self._buffers[path] = lines[-1]

        is_primary = self._is_primary_conversation(path)
        for raw_line in lines[:-1]:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                obj = json.loads(raw_line)
            except Exception:
                continue
            if obj.get("source") == "USER_EXPLICIT":
                self._primary_convs.add(path)
                is_primary = True
            self._process_step(path, obj, is_primary=is_primary)

    def _process_step(self, path: Path, obj: dict, is_primary: bool) -> None:
        step_type = str(obj.get("type") or "")
        source = str(obj.get("source") or "")
        status = str(obj.get("status") or "")
        conv_id = path.parent.parent.parent.name[:8]
        tokens = _extract_tokens(obj)

        if not is_primary:
            if step_type == "PLANNER_RESPONSE" and (obj.get("tool_calls") or []):
                tc = obj["tool_calls"][-1]
                tname = str(tc.get("name") or "subagent")
                self.activity_detected.emit(
                    {
                        "origin": "subagent",
                        "event": "ToolStart",
                        "tool": tname,
                        "detail": _extract_tool_detail(tc),
                        "tokens": tokens,
                        "conv": conv_id,
                        "ts": time.time(),
                    }
                )
            return

        if step_type == "USER_INPUT" and source == "USER_EXPLICIT":
            prompt = _extract_user_prompt(str(obj.get("content") or ""))
            self.activity_detected.emit(
                {
                    "origin": "transcript",
                    "event": "Thinking",
                    "prompt": prompt,
                    "detail": "收到新指令，思考冒泡中…",
                    "tokens": 0,
                    "conv": conv_id,
                    "ts": time.time(),
                }
            )
            return

        if step_type == "PLANNER_RESPONSE":
            tool_calls = obj.get("tool_calls") or []
            content = str(obj.get("content") or "").strip()

            if status == "ERROR":
                self.activity_detected.emit(
                    {
                        "origin": "transcript",
                        "event": "Error",
                        "error": "模型响应遇到错误",
                        "tokens": tokens,
                        "conv": conv_id,
                        "ts": time.time(),
                    }
                )
            elif tool_calls:
                last_tc = tool_calls[-1] if isinstance(tool_calls[-1], dict) else {}
                tool_name = str(last_tc.get("name") or "tool")
                detail = _extract_tool_detail(last_tc)
                self.activity_detected.emit(
                    {
                        "origin": "transcript",
                        "event": "ToolStart",
                        "tool": tool_name,
                        "detail": detail,
                        "tokens": tokens,
                        "conv": conv_id,
                        "ts": time.time(),
                    }
                )
            elif content and status == "DONE":
                self.activity_detected.emit(
                    {
                        "origin": "transcript",
                        "event": "TurnComplete",
                        "detail": content[:32].replace("\n", " "),
                        "tokens": tokens,
                        "conv": conv_id,
                        "ts": time.time(),
                    }
                )
            else:
                self.activity_detected.emit(
                    {
                        "origin": "transcript",
                        "event": "Thinking",
                        "detail": "深度思考碎碎念中…",
                        "tokens": tokens,
                        "conv": conv_id,
                        "ts": time.time(),
                    }
                )
            return

        if step_type == "GENERIC":
            content = str(obj.get("content") or "")
            has_error = status == "ERROR"
            if not has_error:
                m = _EXIT_CODE_RE.search(content)
                if m and m.group(1) != "0":
                    has_error = True

            if has_error:
                self.activity_detected.emit(
                    {
                        "origin": "transcript",
                        "event": "ToolError",
                        "error": "刚才的工具执行出错啦",
                        "tokens": 0,
                        "conv": conv_id,
                        "ts": time.time(),
                    }
                )
            else:
                self.activity_detected.emit(
                    {
                        "origin": "transcript",
                        "event": "Thinking",
                        "detail": "正在分析执行结果…",
                        "tokens": 0,
                        "conv": conv_id,
                        "ts": time.time(),
                    }
                )
