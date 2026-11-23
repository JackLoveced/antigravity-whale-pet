"""Antigravity × DeepSeek 鲸鱼娘（吃白饭的蓝色大肥鱼）— Main PyQt6 Desktop Pet."""

from __future__ import annotations

import datetime
import json
import math
import platform
import random
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import List, Optional

try:
    import winsound
except ImportError:
    winsound = None  # type: ignore

from PyQt6.QtCore import QObject, QPoint, QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QAction,
    QColor,
    QFont,
    QFontDatabase,
    QFontMetrics,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
)
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from antigravity_whale_pet.assets_manager import (
    count_webm_clips,
    fetch_assets,
    resolve_assets_dir,
)
from antigravity_whale_pet.lifecycle import (
    disable_autostart,
    enable_autostart,
    is_antigravity_running,
    is_autostart_enabled,
)
from antigravity_whale_pet.protocol import (
    PET_HOST,
    PET_PORT,
    STATE_CELEBRATE,
    STATE_DRAGGED,
    STATE_ERROR,
    STATE_IDLE,
    STATE_PETTED,
    STATE_SLEEP,
    STATE_THINKING,
    STATE_WORKING,
)
from antigravity_whale_pet.watcher import AntigravityLiveWatcher
from antigravity_whale_pet.webm_player import WebmAnimationPlayer


# --- Animation clip groups from PC2005-cloud/dsh-pet (MIT) ---
CLIP_IDLE_MAIN = "待机呼吸休闲"
CLIP_IDLE_VARIETY = [
    "东张西望",
    "原地专心玩魔方",
    "鲸鱼吐泡泡特效",
    "悠闲哼歌",
    "女仆屈膝礼仪",
    "优雅女仆舞",
    "可爱宅舞",
    "轻快摇摆舞",
    "撸猫",
    "吃白饭",
    "吃Token",
    "吹气球",
    "凭空生花",
    "小提琴演奏",
    "荡秋千",
    "三球抛接",
    "吹笛子",
    "原地敲击桌面互动",
    "照镜子",
    "用鲸鱼尾巴拍打地面",
]
CLIP_THINKING = ["工作状态-思考冒泡", "深度思考碎碎念", "工作状态-原地踱步张望"]
CLIP_CODE_EDIT = ["写代码"]
CLIP_CODE_READ = ["工作状态-清点归档", "轻快记录"]
CLIP_TOOL_BUSY = ["工作状态-忙碌点按", "碎碎念-对屏碎碎念"]
CLIP_CELEBRATE = ["工作状态-雀跃庆祝", "放烟花", "点击回应-开心跃动"]
CLIP_ERROR = ["工作状态-垂头叹气冒汗", "玩游戏气急败坏", "被吓一跳"]
CLIP_CLICK = [
    "点击回应-开心跃动",
    "点击回应-害羞惊讶",
    "点击回应-挠痒咯咯笑",
    "点击回应-傲娇生气",
    "点击回应-元气挥手",
]
CLIP_DRAG = "被鼠标拖拽悬空反馈"
CLIP_LAND = "原地重力下蹲压缩"
CLIP_WALK = ["开心小跑", "螃蟹走路"]
CLIP_SLEEP_START = "睡觉-开始"
CLIP_SLEEP_LOOP = "睡觉-循环"
CLIP_SLEEP_WAKE = "打瞌睡被惊醒"


TOOL_FRIENDLY_NAMES = {
    "read_file": "读文件",
    "view_file": "看代码",
    "write_file": "写新文件",
    "edit_file": "改代码",
    "run_command": "跑终端",
    "search_web": "查资料",
    "grep_search": "搜代码",
    "find_by_name": "找文件",
    "invoke_subagent": "派分身",
    "run_workflow": "跑工作流",
    "ask_question": "向你确认",
    "generate_image": "画插图",
}

CLICK_LINES = [
    "别戳啦，大肥鱼要变圆了！(≧▽≦)",
    "干嘛戳人家！是不是该喂 Token 了？",
    "嘿嘿，好痒呀~ ♡",
    "哼，才不是吃白饭的大肥鱼呢！",
    "在呢在呢！随时帮你盯 Antigravity~",
]

IDLE_LINES = [
    "Antigravity 待命中，随时可以开工~",
    "咕噜咕噜…有点想吃白饭（和 Token）了~",
    "双击我可以点播全部 114 个动作哦！",
    "记得喝口水、保护好颈椎呀~",
    "你这吃白饭的蓝色大肥鱼正在待机中…",
]


def _fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


class HookListener(QObject):
    """Background UDP listener receiving Antigravity lifecycle hook events."""

    event_received = pyqtSignal(dict)
    bind_failed = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self._stop = threading.Event()
        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass

    def _run(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((PET_HOST, PET_PORT))
        except OSError as exc:
            self.bind_failed.emit(str(exc))
            sock.close()
            return

        sock.settimeout(0.4)
        self._sock = sock
        while not self._stop.is_set():
            try:
                data, _ = sock.recvfrom(8192)
                payload = json.loads(data.decode("utf-8", errors="replace"))
                if isinstance(payload, dict):
                    self.event_received.emit(payload)
            except socket.timeout:
                continue
            except OSError:
                break
            except Exception:
                continue


class MonitorDialog(QWidget):
    """Control & live Antigravity monitoring panel with 114-animation player."""

    preview_state_requested = pyqtSignal(str, str, str)
    play_clip_requested = pyqtSignal(str)

    def __init__(self, all_clips: List[str]) -> None:
        super().__init__()
        self.setWindowTitle("Antigravity × DeepSeek 鲸鱼娘（大肥鱼）控制台")
        self.resize(500, 480)
        self.setStyleSheet(
            """
            QWidget {
                background-color: #0F172A;
                color: #E2E8F0;
                font-family: "Microsoft YaHei UI", "PingFang SC", "Segoe UI", sans-serif;
            }
            QFrame#card {
                background-color: #1E293B;
                border: 1px solid #334155;
                border-radius: 10px;
            }
            QPushButton {
                background-color: #1E293B;
                color: #E2E8F0;
                border: 1px solid #3B82F6;
                border-radius: 7px;
                padding: 6px 9px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #2563EB;
                color: #FFFFFF;
            }
            QComboBox {
                background-color: #1E293B;
                color: #F1F5F9;
                border: 1px solid #475569;
                border-radius: 7px;
                padding: 5px 8px;
            }
            QPlainTextEdit {
                background-color: #0B1120;
                color: #93C5FD;
                border: 1px solid #334155;
                border-radius: 8px;
                font-family: Consolas, Menlo, monospace;
                font-size: 12px;
                padding: 6px;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(9)

        header = QLabel("🐋 Antigravity × DeepSeek 鲸鱼娘 · 实时状态与 114 动作面板")
        header.setFont(QFont("Microsoft YaHei UI", 11, QFont.Weight.Bold))
        root.addWidget(header)

        self.live_lbl = QLabel("● 实时会话监控初始化中…")
        self.live_lbl.setStyleSheet("color: #34D399; font-size: 12px;")
        root.addWidget(self.live_lbl)

        self.hook_lbl = QLabel(
            f"● Hook UDP 监听中: udp://{PET_HOST}:{PET_PORT}  |  素材源自 PC2005-cloud/dsh-pet (MIT)"
        )
        self.hook_lbl.setStyleSheet("color: #60A5FA; font-size: 11px;")
        root.addWidget(self.hook_lbl)

        stats_card = QFrame()
        stats_card.setObjectName("card")
        stats_layout = QHBoxLayout(stats_card)
        stats_layout.setContentsMargins(10, 8, 10, 8)
        self.stat_think = self._make_stat("思考", "0")
        self.stat_tool = self._make_stat("调工具", "0")
        self.stat_done = self._make_stat("完工", "0")
        self.stat_tokens = self._make_stat("炫掉 Token", "0")
        for w in (self.stat_think[0], self.stat_tool[0], self.stat_done[0], self.stat_tokens[0]):
            stats_layout.addWidget(w)
        root.addWidget(stats_card)

        preview_title = QLabel("工作状态 & 投喂一键测试：")
        preview_title.setStyleSheet("color: #94A3B8; font-size: 12px;")
        root.addWidget(preview_title)

        row1 = QHBoxLayout()
        row2 = QHBoxLayout()
        quick_btns = [
            ("💭 思考冒泡", STATE_THINKING, "工作状态-思考冒泡", "鲸鱼娘深度思考冒泡中…"),
            ("💻 写代码", STATE_WORKING, "写代码", "正在改代码: app.py"),
            ("📂 清点归档", STATE_WORKING, "工作状态-清点归档", "正在读文件查资料…"),
            ("🎉 雀跃庆祝", STATE_CELEBRATE, "工作状态-雀跃庆祝", "大功告成！快来看看回复吧~"),
            ("💦 垂头冒汗", STATE_ERROR, "工作状态-垂头叹气冒汗", "哎呀，刚才命令出错啦！"),
            ("🍚 吃白饭/Token", STATE_PETTED, "吃Token", "啊呜啊呜~ 炫 Token 真香！"),
        ]
        for idx, (label, st, clip, msg) in enumerate(quick_btns):
            b = QPushButton(label)
            b.clicked.connect(
                lambda _c=False, s=st, cl=clip, m=msg: self.preview_state_requested.emit(s, cl, m)
            )
            (row1 if idx < 3 else row2).addWidget(b)
        root.addLayout(row1)
        root.addLayout(row2)

        juke_row = QHBoxLayout()
        self.clip_combo = QComboBox()
        self.clip_combo.setEditable(True)
        self.clip_combo.addItems(all_clips)
        btn_play = QPushButton("▶ 播放动作")
        btn_play.clicked.connect(lambda: self.play_clip_requested.emit(self.clip_combo.currentText()))
        btn_rand = QPushButton("🎲 随机整活")
        btn_rand.clicked.connect(
            lambda: self.play_clip_requested.emit(random.choice(all_clips)) if all_clips else None
        )
        juke_row.addWidget(self.clip_combo, 1)
        juke_row.addWidget(btn_play)
        juke_row.addWidget(btn_rand)
        root.addLayout(juke_row)

        log_title = QLabel("实时 Antigravity 状态事件流：")
        log_title.setStyleSheet("color: #94A3B8; font-size: 12px;")
        root.addWidget(log_title)

        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setPlaceholderText("你在 Antigravity 里提问、调工具、写代码或完工时，状态会实时同步到这里…")
        root.addWidget(self.log_box)

    def _make_stat(self, name: str, val: str):
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        num = QLabel(val)
        num.setAlignment(Qt.AlignmentFlag.AlignCenter)
        num.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        num.setStyleSheet("color: #60A5FA;")
        lbl = QLabel(name)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("color: #94A3B8; font-size: 11px;")
        lay.addWidget(num)
        lay.addWidget(lbl)
        return box, num

    def update_stats(self, think: int, tool: int, done: int, tokens: int) -> None:
        self.stat_think[1].setText(str(think))
        self.stat_tool[1].setText(str(tool))
        self.stat_done[1].setText(str(done))
        self.stat_tokens[1].setText(_fmt_tokens(tokens))

    def append_log(self, line: str) -> None:
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_box.appendPlainText(f"[{ts}] {line}")


class WhaleMaidPetWindow(QWidget):
    """Frameless transparent floating DeepSeek 鲸鱼娘 desktop pet."""

    def __init__(
        self,
        assets_dir: Path,
        initial_scale: float = 1.0,
        follow_antigravity: bool = True,
    ) -> None:
        super().__init__()
        self.assets_dir = assets_dir
        self.player = WebmAnimationPlayer(assets_dir)
        self.font_path = assets_dir / "fonts" / "上首软糖体.ttf"
        self.sound_click_path = assets_dir / "sound" / "click-duck.wav"
        self.icon_path = assets_dir / "logo.png"
        self.bubble_font_family = self._load_custom_font()

        # Core state machine
        self.state: str = STATE_IDLE
        self.state_until: float = 0.0
        self.last_activity: float = time.time()
        self._one_shot_return_idle: bool = False
        self._next_idle_variety_at: float = time.time() + random.uniform(14.0, 24.0)
        self._sleep_phase: str = ""

        # Preferences
        self.pet_scale: float = max(0.5, min(2.0, initial_scale))
        self.auto_walk: bool = True
        self.always_on_top: bool = True
        self.show_bubbles: bool = True
        self.sound_enabled: bool = True
        self.follow_antigravity: bool = follow_antigravity
        self._agy_missed_checks: int = 0
        self._agy_seen_running: bool = is_antigravity_running() if follow_antigravity else False

        # Orientation & spring bounce
        self.facing_left: bool = False
        self.scale_x: float = 1.0
        self.scale_y: float = 1.0
        self.vel_sx: float = 0.0
        self.vel_sy: float = 0.0
        self.t: float = 0.0

        # Speech bubble & live status capsule
        self.bubble_text: str = "哈喽！吃白饭的蓝色大肥鱼已连上 Antigravity~"
        self.bubble_until: float = time.time() + 5.5
        self.bubble_alpha: float = 1.0
        self.status_badge: str = "Antigravity · 待命中"

        # Drag + Throw Physics
        self._dragging: bool = False
        self._drag_offset: QPoint = QPoint()
        self._drag_moved: bool = False
        self._drag_samples: List[tuple[float, float, float]] = []
        self._thrown: bool = False
        self._phys_vx: float = 0.0
        self._phys_vy: float = 0.0
        self._phys_x: float = 0.0
        self._phys_y: float = 0.0

        # Autonomous walk
        self._walk_vx: float = 0.0
        self._walk_until: float = time.time() + random.uniform(8.0, 15.0)

        # Stats
        self.count_think = 0
        self.count_tool = 0
        self.count_done = 0
        self.count_tokens = 0

        # Window setup
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setMouseTracking(True)
        self._apply_window_flags()
        self._resize_for_scale()
        self._place_initial_position()

        self._play_clip(CLIP_IDLE_MAIN, loop=True)

        self.monitor = MonitorDialog(self.player.all_clip_names())
        self.monitor.preview_state_requested.connect(self._on_preview_state)
        self.monitor.play_clip_requested.connect(self._on_play_custom_clip)
        self._setup_tray()

        # Engine 1: Real-time Antigravity transcript watcher
        self.watcher = AntigravityLiveWatcher(poll_interval=0.20)
        self.watcher.activity_detected.connect(self._on_live_activity)
        self.watcher.watcher_status.connect(self._on_watcher_status)
        self.watcher.start()

        # Engine 2: Antigravity Hooks UDP listener
        self.listener = HookListener()
        self.listener.event_received.connect(self._on_hook_event)
        self.listener.bind_failed.connect(self._on_bind_failed)
        self.listener.start()

        self._last_frame = time.perf_counter()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)

        # Lightweight lifecycle timer: auto-exit when Antigravity closes (if enabled)
        self._lifecycle_timer = QTimer(self)
        self._lifecycle_timer.timeout.connect(self._check_antigravity_lifecycle)
        self._lifecycle_timer.start(2500)

    def _load_custom_font(self) -> str:
        if self.font_path.exists():
            fid = QFontDatabase.addApplicationFont(str(self.font_path))
            if fid != -1:
                fams = QFontDatabase.applicationFontFamilies(fid)
                if fams:
                    return fams[0]
        return "Microsoft YaHei UI"

    def _play_sound(self) -> None:
        if not self.sound_enabled or not self.sound_click_path.exists():
            return
        if winsound is not None:
            try:
                winsound.PlaySound(
                    str(self.sound_click_path),
                    winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
                )
            except Exception:
                pass
        elif platform.system() == "Darwin":
            try:
                subprocess.Popen(
                    ["afplay", str(self.sound_click_path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass

    def _play_clip(self, clip_name: str, loop: bool = True, restart: bool = False) -> None:
        if self.player.has_clip(clip_name):
            self.player.play(clip_name, loop=loop, restart_if_same=restart)
        elif self.player.has_clip(CLIP_IDLE_MAIN):
            self.player.play(CLIP_IDLE_MAIN, loop=True)

    def _trigger_squish(self, strength: float = 0.16) -> None:
        self.vel_sx += strength * 14.0
        self.vel_sy -= strength * 14.0

    def _apply_window_flags(self) -> None:
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if self.always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        was_visible = self.isVisible()
        self.setWindowFlags(flags)
        if was_visible:
            self.show()

    def _resize_for_scale(self) -> None:
        w = int(310 * self.pet_scale)
        h = int(320 * self.pet_scale)
        self.setFixedSize(w, h)

    def _place_initial_position(self) -> None:
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.right() - self.width() - 28
            y = geo.bottom() - self.height() - 10
            self.move(x, y)

    def _setup_tray(self) -> None:
        icon = QIcon(str(self.icon_path)) if self.icon_path.exists() else QIcon()
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip("Antigravity × DeepSeek 鲸鱼娘（大肥鱼）")
        menu = QMenu()
        menu.addAction("🐋 呼唤鲸鱼娘归位").triggered.connect(self._summon_home)
        menu.addAction("📊 打开控制台 & 114 动作面板").triggered.connect(self._open_monitor)
        menu.addAction("🍚 喂白饭 / 喂 Token").triggered.connect(self._feed_token)
        menu.addSeparator()
        menu.addAction("👋 退出鲸鱼娘").triggered.connect(self._quit_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda r: self._open_monitor() if r == QSystemTrayIcon.ActivationReason.DoubleClick else None
        )
        self.tray.show()

    def _summon_home(self) -> None:
        self._thrown = False
        self._walk_vx = 0.0
        self._place_initial_position()
        self.show()
        self.raise_()
        self.say("蓝鲸现世！大肥鱼闪现归位~", duration=3.0)
        self._play_clip("蓝鲸现世", loop=False, restart=True)
        self._one_shot_return_idle = True

    def _open_monitor(self) -> None:
        self.monitor.show()
        self.monitor.raise_()
        self.monitor.activateWindow()

    def _feed_token(self) -> None:
        clip = random.choice(["吃Token", "吃白饭", "吃饭·碗饭", "大口吃零食"])
        self._enter_one_shot(
            STATE_PETTED,
            clip,
            bubble="啊呜啊呜~ 投喂大肥鱼最幸福啦！",
            badge="投喂中 · 炫饭",
        )

    def _quit_app(self) -> None:
        self.watcher.stop()
        self.listener.stop()
        self.player.close()
        self.tray.hide()
        QApplication.quit()

    def say(self, text: str, duration: float = 4.5) -> None:
        if not self.show_bubbles:
            return
        self.bubble_text = text
        self.bubble_until = time.time() + duration

    def _enter_state(
        self,
        new_state: str,
        clip_name: str,
        loop: bool = True,
        duration: float = 0.0,
        bubble: str = "",
        badge: str = "",
    ) -> None:
        self.state = new_state
        self.state_until = (time.time() + duration) if duration > 0 else 0.0
        self.status_badge = badge
        self.last_activity = time.time()
        self._one_shot_return_idle = not loop
        self._walk_vx = 0.0
        self._sleep_phase = ""
        self._play_clip(clip_name, loop=loop, restart=True)
        if bubble:
            self.say(bubble, duration=max(4.5, duration if duration > 0 else 6.0))

    def _enter_one_shot(
        self, new_state: str, clip_name: str, bubble: str = "", badge: str = ""
    ) -> None:
        self.state = new_state
        self.state_until = 0.0
        if badge:
            self.status_badge = badge
        self.last_activity = time.time()
        self._one_shot_return_idle = True
        self._walk_vx = 0.0
        self._play_clip(clip_name, loop=False, restart=True)
        if bubble:
            self.say(bubble, duration=4.5)

    def _on_preview_state(self, st: str, clip: str, msg: str) -> None:
        badge_map = {
            STATE_THINKING: "Antigravity · 思考中",
            STATE_WORKING: f"工作中 · {clip}",
            STATE_CELEBRATE: "Antigravity · 完工！",
            STATE_ERROR: "Antigravity · 报错",
            STATE_PETTED: "投喂大肥鱼中",
        }
        loop = st in (STATE_THINKING, STATE_WORKING)
        dur = 8.0 if loop else 0.0
        self._enter_state(st, clip, loop=loop, duration=dur, bubble=msg, badge=badge_map.get(st, "预览模式"))
        self.monitor.append_log(f"[预览] {st} -> {clip}.webm")

    def _on_play_custom_clip(self, clip_name: str) -> None:
        if not self.player.has_clip(clip_name):
            return
        self._enter_one_shot(
            STATE_PETTED,
            clip_name,
            bubble=f"正在表演：{clip_name}~",
            badge=f"动作 · {clip_name}",
        )
        self.monitor.append_log(f"[点播] {clip_name}.webm")

    def _on_watcher_status(self, msg: str) -> None:
        self.monitor.live_lbl.setText(f"● {msg}")
        self.monitor.append_log(f"[系统] {msg}")

    def _on_bind_failed(self, err: str) -> None:
        self.monitor.hook_lbl.setText(f"● Hook UDP {PET_PORT} 占用（实时日志监控仍正常工作）")
        self.monitor.hook_lbl.setStyleSheet("color: #FBBF24; font-size: 11px;")

    def _pick_tool_clip(self, tool: str) -> str:
        if tool in ("edit_file", "write_file"):
            return random.choice(CLIP_CODE_EDIT)
        if tool in ("read_file", "view_file", "grep_search", "find_by_name"):
            return random.choice(CLIP_CODE_READ)
        return random.choice(CLIP_TOOL_BUSY)

    def _on_live_activity(self, payload: dict) -> None:
        event = str(payload.get("event") or "")
        origin = str(payload.get("origin") or "transcript")
        tool = str(payload.get("tool") or "")
        detail = str(payload.get("detail") or "")
        prompt = str(payload.get("prompt") or "")
        error = str(payload.get("error") or "")
        tokens = int(payload.get("tokens") or 0)

        if tokens > 0:
            self.count_tokens += tokens

        self._thrown = False
        self._walk_vx = 0.0
        self.last_activity = time.time()

        if event == "Thinking":
            self.count_think += 1
            clip = random.choice(CLIP_THINKING)
            if prompt:
                short_p = f"「{prompt[:18]}…」" if len(prompt) > 18 else f"「{prompt}」"
                bubble = f"收到！深度思考冒泡中…\n{short_p}"
            else:
                bubble = detail or "鲸鱼娘深度思考碎碎念中…"
            self._enter_state(
                STATE_THINKING,
                clip,
                loop=True,
                duration=120.0,
                bubble=bubble,
                badge="Antigravity · 深度思考中",
            )
            self.monitor.append_log(f"[实时] 思考: {prompt or detail} ({clip})")

        elif event == "ToolStart":
            self.count_tool += 1
            cn_tool = TOOL_FRIENDLY_NAMES.get(tool, tool or "工具")
            clip = self._pick_tool_clip(tool)
            prefix = "分身" if origin == "subagent" else "正在"
            bubble = f"{prefix}{cn_tool}: {detail}" if detail else f"{prefix}执行 {cn_tool}…"
            self._enter_state(
                STATE_WORKING,
                clip,
                loop=True,
                duration=90.0,
                bubble=bubble,
                badge=f"工作中 · {cn_tool}",
            )
            self.monitor.append_log(f"[实时] 工具: {tool} ({detail or '-'}) -> {clip}")

        elif event in ("ToolError", "Error"):
            clip = random.choice(CLIP_ERROR)
            self._enter_one_shot(
                STATE_ERROR,
                clip,
                bubble=error or "呜哇，刚才执行报错啦！",
                badge="Antigravity · 报错",
            )
            self.monitor.append_log(f"[实时] 异常: {error}")

        elif event == "TurnComplete":
            self.count_done += 1
            tok_note = f"（本轮炫了 {_fmt_tokens(tokens)} Token）" if tokens > 0 else ""
            clip = random.choice(CLIP_CELEBRATE)
            self._enter_one_shot(
                STATE_CELEBRATE,
                clip,
                bubble=f"大功告成！快来看看回复吧~ {tok_note}",
                badge="Antigravity · 回复完成",
            )
            self.monitor.append_log(f"[实时] 完工! +{tokens} tokens -> {clip}")

        self.monitor.update_stats(
            self.count_think, self.count_tool, self.count_done, self.count_tokens
        )

    def _on_hook_event(self, payload: dict) -> None:
        event = str(payload.get("event") or "")
        tool = str(payload.get("tool") or "")
        error = str(payload.get("error") or "")
        reason = str(payload.get("reason") or "")

        if event == "SessionStart":
            self._enter_one_shot(
                STATE_CELEBRATE,
                "蓝鲸现世",
                bubble="新会话开启，蓝鲸现世！",
                badge="Antigravity · 新会话",
            )
            self.monitor.append_log("[Hook] SessionStart")
        elif event == "PreInvocation" and self.state != STATE_THINKING:
            self._enter_state(
                STATE_THINKING,
                "工作状态-思考冒泡",
                loop=True,
                duration=120.0,
                bubble="深度思考冒泡中…",
                badge="Antigravity · 深度思考中",
            )
        elif event == "PostToolUse" and error:
            cn_tool = TOOL_FRIENDLY_NAMES.get(tool, tool or "工具")
            self._enter_one_shot(
                STATE_ERROR,
                "工作状态-垂头叹气冒汗",
                bubble=f"哎呀，{cn_tool} 报错啦！",
                badge=f"报错 · {cn_tool}",
            )
        elif event == "AntigravityClosed":
            if self.follow_antigravity:
                self._quit_app()
        elif event == "Stop" and reason == "USER_CANCELED":
            self.state = STATE_IDLE
            self.status_badge = "Antigravity · 待命中"
            self._play_clip(CLIP_IDLE_MAIN, loop=True)
            self.say("收到，先停下来歇会儿~", duration=3.0)

    def _return_to_idle(self) -> None:
        self.state = STATE_IDLE
        self.state_until = 0.0
        self._one_shot_return_idle = False
        tok_badge = (
            f"待命中 · 已炫 {_fmt_tokens(self.count_tokens)} Tok"
            if self.count_tokens > 0
            else "Antigravity · 待命中"
        )
        self.status_badge = tok_badge
        self._play_clip(CLIP_IDLE_MAIN, loop=True)
        self._next_idle_variety_at = time.time() + random.uniform(16.0, 28.0)

    def _tick(self) -> None:
        now = time.perf_counter()
        dt = min(0.05, max(0.001, now - self._last_frame))
        self._last_frame = now
        self.t += dt
        wall_now = time.time()

        clip_ended = self.player.advance(dt)
        if clip_ended:
            if self._sleep_phase == "start":
                self._sleep_phase = "loop"
                self._play_clip(CLIP_SLEEP_LOOP, loop=True)
            elif self._one_shot_return_idle and not self._dragging and not self._thrown:
                self._return_to_idle()

        if self.state_until > 0 and wall_now >= self.state_until and not self._dragging:
            self._return_to_idle()

        # Spring squish physics
        stiffness, damping = 185.0, 12.5
        ax = (1.0 - self.scale_x) * stiffness - self.vel_sx * damping
        ay = (1.0 - self.scale_y) * stiffness - self.vel_sy * damping
        self.vel_sx += ax * dt
        self.vel_sy += ay * dt
        self.scale_x = max(0.76, min(1.26, self.scale_x + self.vel_sx * dt))
        self.scale_y = max(0.76, min(1.26, self.scale_y + self.vel_sy * dt))

        # Throw gravity + wall bounce physics
        if self._thrown:
            screen = QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()
            if screen:
                geo = screen.availableGeometry()
                self._phys_vy += 1450.0 * dt
                self._phys_x += self._phys_vx * dt
                self._phys_y += self._phys_vy * dt

                bounced = False
                if self._phys_x < geo.left():
                    self._phys_x = float(geo.left())
                    self._phys_vx = abs(self._phys_vx) * 0.68
                    self.facing_left = False
                    bounced = True
                elif self._phys_x + self.width() > geo.right():
                    self._phys_x = float(geo.right() - self.width())
                    self._phys_vx = -abs(self._phys_vx) * 0.68
                    self.facing_left = True
                    bounced = True

                if self._phys_y < geo.top():
                    self._phys_y = float(geo.top())
                    self._phys_vy = abs(self._phys_vy) * 0.6
                    bounced = True

                floor_y = float(geo.bottom() - self.height() - 6)
                if self._phys_y >= floor_y:
                    self._phys_y = floor_y
                    if abs(self._phys_vy) > 220.0:
                        self._phys_vy = -abs(self._phys_vy) * 0.45
                        self._phys_vx *= 0.72
                        self._trigger_squish(0.22)
                    else:
                        self._thrown = False
                        self._trigger_squish(0.24)
                        self._enter_one_shot(
                            STATE_PETTED,
                            CLIP_LAND,
                            bubble="咚！安全着陆~",
                            badge="着陆回弹中",
                        )

                if bounced:
                    self._trigger_squish(0.18)
                self.move(int(round(self._phys_x)), int(round(self._phys_y)))

        elif self.state == STATE_IDLE and not self._dragging:
            if (wall_now - self.last_activity) > 300.0:
                self.state = STATE_SLEEP
                self._sleep_phase = "start"
                self._walk_vx = 0.0
                self.status_badge = "鲸鱼娘 · 小憩沉眠中"
                self._play_clip(CLIP_SLEEP_START, loop=False, restart=True)
                self.say("呼噜呼噜…先眯一会儿，开工叫我哦~", duration=4.0)
            elif self.auto_walk and abs(self._walk_vx) > 0.5:
                screen = QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()
                if screen:
                    geo = screen.availableGeometry()
                    nx = self.x() + self._walk_vx * dt
                    if nx < geo.left() + 8:
                        nx = geo.left() + 8
                        self._walk_vx = abs(self._walk_vx)
                        self.facing_left = False
                    elif nx + self.width() > geo.right() - 8:
                        nx = geo.right() - self.width() - 8
                        self._walk_vx = -abs(self._walk_vx)
                        self.facing_left = True
                    self.move(int(round(nx)), self.y())
                if wall_now >= self._walk_until:
                    self._walk_vx = 0.0
                    self._walk_until = wall_now + random.uniform(12.0, 22.0)
                    self._play_clip(CLIP_IDLE_MAIN, loop=True)
            else:
                if self.auto_walk and wall_now >= self._walk_until:
                    direction = random.choice([-1.0, 1.0])
                    self._walk_vx = direction * random.uniform(34.0, 52.0)
                    self.facing_left = direction < 0
                    self._walk_until = wall_now + random.uniform(3.0, 5.5)
                    self._play_clip(random.choice(CLIP_WALK), loop=True)
                elif wall_now >= self._next_idle_variety_at:
                    clip = random.choice(CLIP_IDLE_VARIETY)
                    self._next_idle_variety_at = wall_now + random.uniform(22.0, 38.0)
                    self._one_shot_return_idle = True
                    self._play_clip(clip, loop=False, restart=True)
                    if random.random() < 0.35:
                        self.say(random.choice(IDLE_LINES), duration=4.2)

        target_alpha = 1.0 if (self.show_bubbles and wall_now < self.bubble_until) else 0.0
        self.bubble_alpha += (target_alpha - self.bubble_alpha) * min(1.0, dt * 10.0)
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        w = float(self.width())
        h = float(self.height())
        cx = w * 0.5
        cy = h * 0.59

        pix = self.player.current_pixmap()
        if pix is not None and not pix.isNull():
            target_h = 205.0 * self.pet_scale
            aspect = pix.width() / max(1.0, float(pix.height()))
            target_w = target_h * aspect

            painter.save()
            painter.translate(cx, cy)
            flip = -1.0 if self.facing_left else 1.0
            painter.scale(flip * self.scale_x, self.scale_y)
            dst = QRectF(-target_w * 0.5, -target_h * 0.5, target_w, target_h)
            painter.drawPixmap(dst, pix, QRectF(pix.rect()))
            painter.restore()

        if self.status_badge:
            self._draw_status_pill(painter, cx, cy + 104 * self.pet_scale, self.status_badge)

        if self.bubble_text and self.bubble_alpha > 0.02:
            self._draw_speech_bubble(
                painter, w, cy - 96 * self.pet_scale, self.bubble_text, self.bubble_alpha
            )

        painter.end()

    def _draw_status_pill(self, painter: QPainter, cx: float, cy: float, text: str) -> None:
        font = QFont(self.bubble_font_family, 8)
        font.setBold(True)
        painter.setFont(font)
        fm = QFontMetrics(font)
        tw = fm.horizontalAdvance(text)
        th = fm.height()
        pw = tw + 26
        ph = th + 8

        dot_color = {
            STATE_THINKING: QColor("#38BDF8"),
            STATE_WORKING: QColor("#34D399"),
            STATE_CELEBRATE: QColor("#FBBF24"),
            STATE_ERROR: QColor("#F87171"),
            STATE_SLEEP: QColor("#94A3B8"),
        }.get(self.state, QColor("#60A5FA"))

        rect = QRectF(cx - pw * 0.5, cy - ph * 0.5, pw, ph)
        painter.setPen(QPen(QColor(dot_color.red(), dot_color.green(), dot_color.blue(), 190), 1.3))
        painter.setBrush(QColor(15, 23, 42, 224))
        painter.drawRoundedRect(rect, ph * 0.5, ph * 0.5)

        pulse = 0.65 + 0.35 * math.sin(self.t * 6.0)
        dot_c = QColor(dot_color)
        dot_c.setAlpha(int(255 * pulse))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(dot_c)
        painter.drawEllipse(QPointF(rect.left() + 10.5, cy), 3.5, 3.5)

        painter.setPen(QColor("#F1F5F9"))
        painter.drawText(
            QRectF(rect.left() + 17, rect.top(), pw - 20, ph),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            text,
        )

    def _draw_speech_bubble(
        self, painter: QPainter, width: float, bottom_y: float, text: str, alpha: float
    ) -> None:
        painter.save()
        font = QFont(self.bubble_font_family, 9)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)

        max_w = int(width - 20)
        fm = QFontMetrics(font)
        bound = fm.boundingRect(0, 0, max_w - 22, 120, Qt.TextFlag.TextWordWrap, text)
        bw = max(72, min(max_w, bound.width() + 24))
        bh = max(30, bound.height() + 16)

        x = (width - bw) * 0.5
        y = max(4.0, bottom_y - bh)

        rect = QRectF(x, y, bw, bh)
        bg = QColor(15, 23, 42, int(234 * alpha))
        border = QColor(96, 165, 250, int(205 * alpha))
        fg = QColor(241, 245, 249, int(255 * alpha))

        painter.setPen(QPen(border, 1.5))
        painter.setBrush(bg)
        painter.drawRoundedRect(rect, 12, 12)

        cx = width * 0.5
        tri = QPainterPath()
        tri.moveTo(cx - 6, y + bh - 1)
        tri.lineTo(cx, y + bh + 6)
        tri.lineTo(cx + 6, y + bh - 1)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg)
        painter.drawPath(tri)
        painter.setPen(QPen(border, 1.5))
        painter.drawLine(QPointF(cx - 6, y + bh), QPointF(cx, y + bh + 6))
        painter.drawLine(QPointF(cx, y + bh + 6), QPointF(cx + 6, y + bh))

        painter.setPen(fg)
        painter.drawText(
            QRectF(x + 11, y + 6, bw - 22, bh - 12),
            Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
            text,
        )
        painter.restore()

    # --- Mouse Interactions ---

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._thrown = False
            self._drag_moved = False
            self._walk_vx = 0.0
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            gpos = event.globalPosition()
            self._drag_samples = [(time.perf_counter(), gpos.x(), gpos.y())]
            self.last_activity = time.time()
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event.globalPosition().toPoint())
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if not self._dragging:
            return
        gpos = event.globalPosition()
        new_pos = gpos.toPoint() - self._drag_offset
        now = time.perf_counter()
        self._drag_samples.append((now, gpos.x(), gpos.y()))
        self._drag_samples = [s for s in self._drag_samples if now - s[0] <= 0.12]

        if not self._drag_moved and (new_pos - self.pos()).manhattanLength() > 5:
            self._drag_moved = True
            self.state = STATE_DRAGGED
            self._one_shot_return_idle = False
            self._play_clip(CLIP_DRAG, loop=True)
            self.say("呜哇！别拎着大肥鱼甩呀~", duration=2.0)

        self.move(new_pos)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            if self._drag_moved:
                vx, vy = 0.0, 0.0
                if len(self._drag_samples) >= 2:
                    t0, x0, y0 = self._drag_samples[0]
                    t1, x1, y1 = self._drag_samples[-1]
                    dt = max(0.015, t1 - t0)
                    vx = max(-1400.0, min(1400.0, (x1 - x0) / dt))
                    vy = max(-1400.0, min(1400.0, (y1 - y0) / dt))

                if math.hypot(vx, vy) > 360.0:
                    self._thrown = True
                    self._phys_x = float(self.x())
                    self._phys_y = float(self.y())
                    self._phys_vx = vx * 0.78
                    self._phys_vy = vy * 0.78
                    self.say("呀——飞出去啦！！", duration=2.2)
                else:
                    self._trigger_squish(0.20)
                    self._enter_one_shot(STATE_PETTED, CLIP_LAND, bubble="安全放好啦~")
            else:
                self._play_sound()
                self._trigger_squish(0.18)
                if self.state == STATE_SLEEP:
                    self._sleep_phase = ""
                    self._enter_one_shot(
                        STATE_PETTED,
                        CLIP_SLEEP_WAKE,
                        bubble="唔…被叫醒啦！发生什么事了？",
                        badge="Antigravity · 待命中",
                    )
                elif self.state in (STATE_IDLE, STATE_PETTED, STATE_CELEBRATE):
                    clip = random.choice(CLIP_CLICK)
                    self._enter_one_shot(STATE_PETTED, clip, bubble=random.choice(CLICK_LINES))
                else:
                    self.say("正在认真帮 Antigravity 干活呢，别打扰我~", duration=2.4)
            event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self._open_monitor()
            event.accept()

    def _show_context_menu(self, global_pos: QPoint) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(
            """
            QMenu {
                background-color: #0F172A;
                color: #F1F5F9;
                border: 1px solid #3B82F6;
                border-radius: 8px;
                padding: 5px;
                font-family: "Microsoft YaHei UI", "PingFang SC", sans-serif;
            }
            QMenu::item {
                padding: 6px 18px;
                border-radius: 5px;
            }
            QMenu::item:selected {
                background-color: #2563EB;
            }
            """
        )

        menu.addAction("📊 打开控制台 & 114 动作点播").triggered.connect(self._open_monitor)
        menu.addAction("🍚 投喂大肥鱼（吃白饭 / 吃 Token）").triggered.connect(self._feed_token)
        menu.addAction("🎲 随机整活一个动作").triggered.connect(
            lambda: self._on_play_custom_clip(random.choice(self.player.all_clip_names()))
            if self.player.all_clip_names()
            else None
        )

        sub_work = menu.addMenu("🎭 工作状态预览")
        for label, st, clip, msg in [
            ("💭 深度思考冒泡", STATE_THINKING, "工作状态-思考冒泡", "深度思考冒泡中…"),
            ("💻 写代码", STATE_WORKING, "写代码", "正在改代码: app.py"),
            ("📂 清点归档", STATE_WORKING, "工作状态-清点归档", "正在读文件查资料…"),
            ("⌨️ 忙碌点按", STATE_WORKING, "工作状态-忙碌点按", "正在跑终端命令…"),
            ("🎉 雀跃庆祝", STATE_CELEBRATE, "工作状态-雀跃庆祝", "大功告成！"),
            ("💦 垂头叹气冒汗", STATE_ERROR, "工作状态-垂头叹气冒汗", "命令报错啦！"),
            ("💤 小憩沉眠", STATE_SLEEP, "睡觉-循环", "呼噜呼噜…"),
            ("✨ 恢复待机", STATE_IDLE, CLIP_IDLE_MAIN, "恢复待机啦~"),
        ]:
            sub_work.addAction(label).triggered.connect(
                lambda _c=False, s=st, cl=clip, m=msg: self._on_preview_state(s, cl, m)
            )

        menu.addSeparator()

        act_walk = QAction("🌊 自动散步（开心小跑）", self, checkable=True)
        act_walk.setChecked(self.auto_walk)
        act_walk.triggered.connect(self._toggle_walk)
        menu.addAction(act_walk)

        act_top = QAction("📌 始终置顶显示", self, checkable=True)
        act_top.setChecked(self.always_on_top)
        act_top.triggered.connect(self._toggle_top)
        menu.addAction(act_top)

        act_bubble = QAction("💬 显示气泡台词", self, checkable=True)
        act_bubble.setChecked(self.show_bubbles)
        act_bubble.triggered.connect(self._toggle_bubbles)
        menu.addAction(act_bubble)

        act_sound = QAction("🔊 点击音效", self, checkable=True)
        act_sound.setChecked(self.sound_enabled)
        act_sound.triggered.connect(lambda c: setattr(self, "sound_enabled", c))
        menu.addAction(act_sound)

        act_follow = QAction("🔗 随 Antigravity 关闭自动退出", self, checkable=True)
        act_follow.setChecked(self.follow_antigravity)
        act_follow.triggered.connect(self._toggle_follow_antigravity)
        menu.addAction(act_follow)

        act_autostart = QAction("⚡ 随 Antigravity 自动启停（开机守护）", self, checkable=True)
        act_autostart.setChecked(is_autostart_enabled())
        act_autostart.triggered.connect(self._toggle_autostart)
        menu.addAction(act_autostart)

        sub_scale = menu.addMenu("🔍 体型大小")
        for label, sc in [("迷你 (75%)", 0.75), ("标准 (100%)", 1.0), ("大号 (130%)", 1.3)]:
            a = QAction(label, self, checkable=True)
            a.setChecked(abs(self.pet_scale - sc) < 0.05)
            a.triggered.connect(lambda _c=False, s=sc: self._set_scale(s))
            sub_scale.addAction(a)

        menu.addSeparator()
        menu.addAction("👋 让大肥鱼下班（退出）").triggered.connect(self._quit_app)

        menu.exec(global_pos)

    def _toggle_walk(self, checked: bool) -> None:
        self.auto_walk = checked
        if not checked:
            self._walk_vx = 0.0
            if self.state == STATE_IDLE:
                self._play_clip(CLIP_IDLE_MAIN, loop=True)
            self.say("好的，我乖乖待在这里陪你~", duration=2.5)
        else:
            self.say("自由散步开启！", duration=2.5)

    def _toggle_top(self, checked: bool) -> None:
        self.always_on_top = checked
        self._apply_window_flags()

    def _toggle_bubbles(self, checked: bool) -> None:
        self.show_bubbles = checked
        if checked:
            self.say("气泡回来啦~", duration=2.5)

    def _check_antigravity_lifecycle(self) -> None:
        if not self.follow_antigravity:
            return
        if is_antigravity_running():
            self._agy_seen_running = True
            self._agy_missed_checks = 0
        elif self._agy_seen_running:
            self._agy_missed_checks += 1
            if self._agy_missed_checks >= 2:
                self._quit_app()

    def _toggle_follow_antigravity(self, checked: bool) -> None:
        self.follow_antigravity = checked
        self._agy_missed_checks = 0
        if checked:
            self._agy_seen_running = is_antigravity_running()
            self.say("收到！Antigravity 关闭时我也会自动下班~", duration=3.0)
        else:
            self.say("已关闭自动退出，我会一直陪着你~", duration=2.8)

    def _toggle_autostart(self, checked: bool) -> None:
        try:
            if checked:
                enable_autostart(
                    assets_dir=str(self.assets_dir),
                    scale=self.pet_scale,
                    start_now=True,
                )
                self.follow_antigravity = True
                self._agy_seen_running = is_antigravity_running()
                self._agy_missed_checks = 0
                self.say("已开启开机守护！以后随 Antigravity 自动开关~", duration=3.5)
            else:
                disable_autostart()
                self.say("已关闭开机自动守护~", duration=2.8)
        except Exception as exc:
            self.say(f"设置自启失败: {exc}", duration=4.0)

    def _set_scale(self, scale: float) -> None:
        center = self.frameGeometry().center()
        self.pet_scale = scale
        self._resize_for_scale()
        self.move(center.x() - self.width() // 2, center.y() - self.height() // 2)
        self._trigger_squish(0.16)


def main(
    assets_dir: Optional[str | Path] = None,
    scale: float = 1.0,
    follow_antigravity: bool = True,
) -> None:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    resolved = resolve_assets_dir(assets_dir)
    if count_webm_clips(resolved) == 0:
        reply = QMessageBox.question(
            None,
            "首次启动 — 下载鲸鱼娘动画素材",
            (
                "检测到本地尚未下载 DeepSeek 鲸鱼娘 114 段开源透明动画（约 59 MB，MIT 协议）。\n\n"
                f"将自动下载到：\n{resolved}\n\n"
                "是否立即下载并启动？"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            sys.exit(0)
        try:
            resolved = fetch_assets(target_dir=resolved)
        except Exception as exc:
            QMessageBox.critical(
                None,
                "素材下载失败",
                f"下载动画素材失败：\n{exc}\n\n"
                "你也可以在终端运行：\n"
                "  agy-pet fetch-assets --mirror https://ghfast.top/",
            )
            sys.exit(1)

    pet = WhaleMaidPetWindow(
        assets_dir=resolved,
        initial_scale=scale,
        follow_antigravity=follow_antigravity,
    )
    pet.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
