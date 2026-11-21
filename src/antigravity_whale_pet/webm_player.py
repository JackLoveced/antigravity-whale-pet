"""Zero-RAM, instant-switch streaming VP9+Alpha WebM player using PyAV (libvpx-vp9)."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterator, List, Optional

import av
import numpy as np
from PyQt6.QtGui import QImage, QPixmap

# Center crop inside 640x360 transparent frame (keeps wide props & full hair/tail)
CROP_X0 = 110
CROP_X1 = 530
CROP_Y0 = 0
CROP_Y1 = 360


def discover_webm_clips(webm_dir: Path) -> Dict[str, Path]:
    clips: Dict[str, Path] = {}
    if not webm_dir.is_dir():
        return clips
    for p in sorted(webm_dir.rglob("*.webm")):
        clips[p.stem] = p
    return clips


def _frame_to_pixmap(frame: av.VideoFrame) -> QPixmap:
    rgba = frame.to_ndarray(format="rgba")
    h, w, _ = rgba.shape
    if w >= CROP_X1 and h >= CROP_Y1:
        sub = np.ascontiguousarray(rgba[CROP_Y0:CROP_Y1, CROP_X0:CROP_X1, :])
    else:
        sub = np.ascontiguousarray(rgba)
    sh, sw, _ = sub.shape
    qimg = QImage(
        sub.data,
        sw,
        sh,
        sw * 4,
        QImage.Format.Format_RGBA8888,
    ).copy()
    return QPixmap.fromImage(qimg)


class _WebmStream:
    """Single open libvpx-vp9 stream yielding transparent QPixmaps one frame at a time."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.fps: float = 24.0
        self._container: Optional[av.container.InputContainer] = None
        self._gen: Optional[Iterator[QPixmap]] = None
        self._open()

    def _open(self) -> None:
        self.close()
        container = av.open(str(self.path))
        stream = container.streams.video[0]
        if stream.average_rate:
            fps = float(stream.average_rate)
            if 8.0 <= fps <= 60.0:
                self.fps = fps
        self._container = container
        self._gen = self._iter_frames(container)

    @staticmethod
    def _iter_frames(container: av.container.InputContainer) -> Iterator[QPixmap]:
        # Explicitly use libvpx-vp9 so VP9 alpha side-data (yuva420p) is decoded!
        codec = av.codec.Codec("libvpx-vp9", "r")
        ctx = codec.create()
        for pkt in container.demux(video=0):
            if pkt.dts is None:
                continue
            for frame in ctx.decode(pkt):
                yield _frame_to_pixmap(frame)
        for frame in ctx.decode(None):
            yield _frame_to_pixmap(frame)

    def next_frame(self) -> Optional[QPixmap]:
        if self._gen is None:
            return None
        try:
            return next(self._gen)
        except StopIteration:
            return None
        except Exception:
            return None

    def rewind(self) -> None:
        self._open()

    def close(self) -> None:
        self._gen = None
        if self._container is not None:
            try:
                self._container.close()
            except Exception:
                pass
            self._container = None


class WebmAnimationPlayer:
    """Instant-switch streaming transparent WebM player across all dsh-pet clips."""

    def __init__(self, assets_dir: Path) -> None:
        self.assets_dir = assets_dir
        self.clips: Dict[str, Path] = discover_webm_clips(assets_dir / "webm")
        self.current_name: str = ""
        self._stream: Optional[_WebmStream] = None
        self._current_pixmap: Optional[QPixmap] = None
        self._fps: float = 24.0
        self._time_accum: float = 0.0
        self._loop: bool = True
        self._finished: bool = False

    def has_clip(self, name: str) -> bool:
        return name in self.clips

    def all_clip_names(self) -> List[str]:
        return sorted(self.clips.keys())

    def play(self, name: str, loop: bool = True, restart_if_same: bool = False) -> bool:
        if name == self.current_name and not restart_if_same and self._stream is not None:
            self._loop = loop
            return True
        path = self.clips.get(name)
        if path is None:
            return False
        try:
            new_stream = _WebmStream(path)
            first = new_stream.next_frame()
            if first is None:
                new_stream.close()
                return False
        except Exception:
            return False

        if self._stream is not None:
            self._stream.close()
        self._stream = new_stream
        self._current_pixmap = first
        self._fps = new_stream.fps
        self.current_name = name
        self._time_accum = 0.0
        self._loop = loop
        self._finished = False
        return True

    def advance(self, dt: float) -> bool:
        """Advance playback by dt seconds. Returns True when a non-looping clip finishes."""
        if self._stream is None or self._finished:
            return False
        frame_dur = 1.0 / max(1.0, self._fps)
        self._time_accum += dt
        steps = int(self._time_accum / frame_dur)
        if steps <= 0:
            return False
        steps = min(steps, 3)
        self._time_accum -= steps * frame_dur

        for _ in range(steps):
            pix = self._stream.next_frame()
            if pix is None:
                if self._loop:
                    self._stream.rewind()
                    pix = self._stream.next_frame()
                    if pix is not None:
                        self._current_pixmap = pix
                else:
                    self._finished = True
                    return True
            else:
                self._current_pixmap = pix
        return False

    def current_pixmap(self) -> Optional[QPixmap]:
        return self._current_pixmap

    def close(self) -> None:
        if self._stream is not None:
            self._stream.close()
            self._stream = None
