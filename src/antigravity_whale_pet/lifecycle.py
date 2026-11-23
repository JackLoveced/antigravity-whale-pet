"""Antigravity process detection, lifecycle watcher daemon, and OS auto-start manager.

Pure Python standard library only (zero PyQt6 / PyAV / numpy imports) so the
background watcher (`agy-pet watch`) uses <10 MB RAM and ~0% CPU while waiting
for Google Antigravity to open.
"""

from __future__ import annotations

import ctypes
import json
import platform
import select
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from antigravity_whale_pet.protocol import PET_HOST, PET_PORT

WATCHER_LOCK_PORT = 39482
AUTOSTART_NAME = "AntigravityWhalePetWatcher"

# Exact process names belonging to Google Antigravity (never matching agy-pet / whale-pet)
_WIN_PROCESS_NAMES = frozenset(
    {
        "antigravity.exe",
        "antigravity-ide.exe",
        "agy.exe",
    }
)
_POSIX_PROCESS_NAMES = frozenset(
    {
        "antigravity",
        "antigravity-ide",
        "agy",
    }
)


def _is_antigravity_running_windows() -> bool:
    """Fast, zero-subprocess Win32 process snapshot check."""
    TH32CS_SNAPPROCESS = 0x00000002
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", ctypes.c_uint32),
            ("cntUsage", ctypes.c_uint32),
            ("th32ProcessID", ctypes.c_uint32),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", ctypes.c_uint32),
            ("cntThreads", ctypes.c_uint32),
            ("th32ParentProcessID", ctypes.c_uint32),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", ctypes.c_uint32),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    kernel32 = ctypes.windll.kernel32
    kernel32.CreateToolhelp32Snapshot.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
    kernel32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    kernel32.Process32FirstW.argtypes = [ctypes.c_void_p, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32FirstW.restype = ctypes.c_int
    kernel32.Process32NextW.argtypes = [ctypes.c_void_p, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32NextW.restype = ctypes.c_int
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int

    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snap or snap == INVALID_HANDLE_VALUE:
        return False

    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        if not kernel32.Process32FirstW(snap, ctypes.byref(entry)):
            return False
        while True:
            exe = entry.szExeFile.lower()
            if exe in _WIN_PROCESS_NAMES:
                return True
            if not kernel32.Process32NextW(snap, ctypes.byref(entry)):
                break
        return False
    finally:
        kernel32.CloseHandle(snap)


def _is_antigravity_running_linux() -> bool:
    """Fast zero-subprocess /proc scan on Linux."""
    proc_root = Path("/proc")
    if not proc_root.is_dir():
        return False
    try:
        for entry in proc_root.iterdir():
            if not entry.name.isdigit():
                continue
            try:
                comm = (entry / "comm").read_text(encoding="utf-8", errors="ignore").strip().lower()
                if comm in _POSIX_PROCESS_NAMES:
                    return True
            except OSError:
                continue
    except OSError:
        return False
    return False


def _is_antigravity_running_macos() -> bool:
    """Lightweight pgrep check on macOS."""
    for name in ("Antigravity", "agy"):
        try:
            res = subprocess.run(
                ["pgrep", "-ix", name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2,
            )
            if res.returncode == 0:
                return True
        except Exception:
            continue
    return False


def is_antigravity_running() -> bool:
    """Return True if Google Antigravity desktop app or CLI is currently running."""
    system = platform.system()
    if system == "Windows":
        return _is_antigravity_running_windows()
    if system == "Linux":
        return _is_antigravity_running_linux()
    if system == "Darwin":
        return _is_antigravity_running_macos()
    return False


def _gui_python_executable() -> str:
    """Return pythonw.exe on Windows (no console window) or sys.executable elsewhere."""
    exe = Path(sys.executable)
    if platform.system() == "Windows" and exe.name.lower() == "python.exe":
        pyw = exe.with_name("pythonw.exe")
        if pyw.exists():
            return str(pyw)
    return str(exe)


def _is_udp_port_in_use(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((PET_HOST, port))
        return False
    except OSError:
        return True
    finally:
        sock.close()


def _acquire_watcher_lock() -> Optional[socket.socket]:
    """Ensure only one `agy-pet watch` daemon runs at a time."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((PET_HOST, WATCHER_LOCK_PORT))
        sock.setblocking(False)
        return sock
    except OSError:
        sock.close()
        return None


def is_watcher_running() -> bool:
    """Return True if an `agy-pet watch` daemon is currently active."""
    return _is_udp_port_in_use(WATCHER_LOCK_PORT)


def stop_watcher_daemon() -> bool:
    """Ask any active `agy-pet watch` daemon to exit cleanly."""
    if not is_watcher_running():
        return False
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(b"STOP_WATCHER", (PET_HOST, WATCHER_LOCK_PORT))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _notify_pet_antigravity_closed() -> None:
    """Tell any running pet instance that Antigravity has closed."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        payload = json.dumps({"event": "AntigravityClosed", "ts": time.time()}).encode("utf-8")
        sock.sendto(payload, (PET_HOST, PET_PORT))
    except OSError:
        pass
    finally:
        sock.close()


def run_watcher_daemon(
    poll_interval: float = 2.0,
    assets_dir: Optional[str] = None,
    scale: float = 1.0,
) -> None:
    """Keep the pet automatically synced with Antigravity's open/close lifecycle.

    - Starts the desktop pet automatically when Antigravity opens (unless one is already open).
    - Closes the desktop pet automatically when Antigravity exits.
    - If the user manually quits the pet while Antigravity is still open,
      respects that choice until Antigravity is closed and opened again.
    """
    lock_sock = _acquire_watcher_lock()
    if lock_sock is None:
        return  # Another watcher instance is already running

    pet_proc: Optional[subprocess.Popen] = None
    dismissed_for_session = False
    missed_checks = 0
    was_running = False

    def _spawn_pet() -> subprocess.Popen:
        cmd = [
            _gui_python_executable(),
            "-m",
            "antigravity_whale_pet",
            "run",
            "--follow-antigravity",
            "--scale",
            str(scale),
        ]
        if assets_dir:
            cmd.extend(["--assets-dir", assets_dir])

        kwargs: dict = {}
        if platform.system() == "Windows":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return subprocess.Popen(cmd, **kwargs)

    def _stop_pet() -> None:
        nonlocal pet_proc
        _notify_pet_antigravity_closed()
        if pet_proc is None:
            return
        if pet_proc.poll() is None:
            try:
                pet_proc.wait(timeout=2.5)
            except Exception:
                try:
                    pet_proc.terminate()
                    pet_proc.wait(timeout=2.0)
                except Exception:
                    try:
                        pet_proc.kill()
                    except Exception:
                        pass
        pet_proc = None

    def _wait_or_stop(timeout: float) -> bool:
        """Sleep up to timeout seconds, returning True if STOP_WATCHER command arrived."""
        try:
            readable, _, _ = select.select([lock_sock], [], [], timeout)
            if readable:
                data, _ = lock_sock.recvfrom(1024)
                if data.strip() == b"STOP_WATCHER":
                    return True
        except Exception:
            time.sleep(timeout)
        return False

    try:
        while True:
            agy_alive = is_antigravity_running()

            # Detect if the user manually closed the pet while Antigravity is still running
            if pet_proc is not None and pet_proc.poll() is not None:
                pet_proc = None
                if agy_alive:
                    dismissed_for_session = True

            if agy_alive:
                missed_checks = 0
                if not was_running:
                    dismissed_for_session = False
                was_running = True

                # Spawn pet only if not dismissed and no existing pet already holds PET_PORT
                if (
                    pet_proc is None
                    and not dismissed_for_session
                    and not _is_udp_port_in_use(PET_PORT)
                ):
                    try:
                        pet_proc = _spawn_pet()
                    except Exception:
                        pet_proc = None
            else:
                if was_running:
                    missed_checks += 1
                    # Require 2 consecutive misses (~4s) to ignore brief app restarts
                    if missed_checks >= 2:
                        was_running = False
                        dismissed_for_session = False
                        _stop_pet()
                else:
                    dismissed_for_session = False

            if _wait_or_stop(poll_interval):
                break
    except KeyboardInterrupt:
        pass
    finally:
        lock_sock.close()


# --- Cross-platform OS Login Auto-Start Management ---

def _win_run_command(assets_dir: Optional[str] = None, scale: float = 1.0) -> str:
    pyw = _gui_python_executable()
    cmd = f'"{pyw}" -m antigravity_whale_pet watch --scale {scale}'
    if assets_dir:
        cmd += f' --assets-dir "{assets_dir}"'
    return cmd


def _macos_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / "com.antigravity.whale-pet.watcher.plist"


def _linux_desktop_path() -> Path:
    return Path.home() / ".config" / "autostart" / "antigravity-whale-pet-watcher.desktop"


def enable_autostart(
    assets_dir: Optional[str] = None,
    scale: float = 1.0,
    start_now: bool = True,
) -> str:
    """Register `agy-pet watch` to run silently on user login."""
    system = platform.system()
    if system == "Windows":
        import winreg

        cmd = _win_run_command(assets_dir=assets_dir, scale=scale)
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.SetValueEx(key, AUTOSTART_NAME, 0, winreg.REG_SZ, cmd)
        location = f"HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\\{AUTOSTART_NAME}"
    elif system == "Darwin":
        plist = _macos_plist_path()
        plist.parent.mkdir(parents=True, exist_ok=True)
        args = [sys.executable, "-m", "antigravity_whale_pet", "watch", "--scale", str(scale)]
        if assets_dir:
            args.extend(["--assets-dir", str(assets_dir)])
        args_xml = "\n".join(f"      <string>{a}</string>" for a in args)
        plist.write_text(
            f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.antigravity.whale-pet.watcher</string>
  <key>ProgramArguments</key>
  <array>
{args_xml}
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
</dict>
</plist>
""",
            encoding="utf-8",
        )
        location = str(plist)
    else:
        desktop = _linux_desktop_path()
        desktop.parent.mkdir(parents=True, exist_ok=True)
        cmd = f'"{sys.executable}" -m antigravity_whale_pet watch --scale {scale}'
        if assets_dir:
            cmd += f' --assets-dir "{assets_dir}"'
        desktop.write_text(
            f"""[Desktop Entry]
Type=Application
Name=Antigravity Whale Pet Watcher
Comment=Auto-start DeepSeek Whale-Girl pet when Google Antigravity opens
Exec={cmd}
X-GNOME-Autostart-enabled=true
""",
            encoding="utf-8",
        )
        location = str(desktop)

    if start_now and not is_watcher_running():
        start_watcher_background(assets_dir=assets_dir, scale=scale)

    return location


def start_watcher_background(assets_dir: Optional[str] = None, scale: float = 1.0) -> bool:
    """Spawn the lightweight `agy-pet watch` daemon in the background."""
    if is_watcher_running():
        return False
    cmd = [
        _gui_python_executable(),
        "-m",
        "antigravity_whale_pet",
        "watch",
        "--scale",
        str(scale),
    ]
    if assets_dir:
        cmd.extend(["--assets-dir", assets_dir])
    kwargs: dict = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if platform.system() == "Windows":
        kwargs["creationflags"] = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0)
        )
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(cmd, **kwargs)
    return True


def disable_autostart(stop_running: bool = True) -> bool:
    """Remove `agy-pet watch` login auto-start registration and stop running daemon."""
    if stop_running:
        stop_watcher_daemon()

    system = platform.system()
    if system == "Windows":
        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                winreg.DeleteValue(key, AUTOSTART_NAME)
            return True
        except FileNotFoundError:
            return False
    elif system == "Darwin":
        plist = _macos_plist_path()
        if plist.exists():
            plist.unlink()
            return True
        return False
    else:
        desktop = _linux_desktop_path()
        if desktop.exists():
            desktop.unlink()
            return True
        return False


def is_autostart_enabled() -> bool:
    """Return True if login auto-start is currently registered."""
    system = platform.system()
    if system == "Windows":
        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_READ,
            ) as key:
                winreg.QueryValueEx(key, AUTOSTART_NAME)
            return True
        except FileNotFoundError:
            return False
    elif system == "Darwin":
        return _macos_plist_path().exists()
    else:
        return _linux_desktop_path().exists()
