"""
PlaybackController  (Now Playing Panel — Right Sidebar)
────────────────────────────────────────────────────────
Shows album art, track info, progress slider, playback controls,
volume slider, and a scrollable queue list.

Drop-in replacement that integrates with the existing AudioPlayerWidget
signals/slots interface.

Signals emitted:
    play_pause_clicked()
    prev_clicked()
    next_clicked()
    seek_requested(position_ms: int)
    volume_changed(volume: int)        0-100
    shuffle_toggled(enabled: bool)
    repeat_toggled(enabled: bool)
    queue_item_double_clicked(file_path: str, metadata: dict)
"""

from __future__ import annotations

import math
from typing import Optional, List, Tuple, Dict, Any

from PyQt5.QtCore import (
    Qt, QTimer, QSize, pyqtSignal, QPropertyAnimation,
    QEasingCurve, QRect
)
from PyQt5.QtGui import (
    QPainter, QPainterPath, QColor, QPixmap, QLinearGradient,
    QBrush, QPen, QFont, QFontMetrics, QRadialGradient
)
from PyQt5.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSlider, QScrollArea, QSizePolicy,
    QGraphicsOpacityEffect
)


# ─────────────────────────────────────────────────────────────────
#  Round album art widget
# ─────────────────────────────────────────────────────────────────
class _AlbumArtWidget(QWidget):
    SIZE = 220   # px

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.SIZE, self.SIZE)
        self._pixmap: Optional[QPixmap] = None

    def set_pixmap(self, px: QPixmap) -> None:
        self._pixmap = px.scaled(
            self.SIZE, self.SIZE,
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation,
        )
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)

        r = self.SIZE
        radius = 20

        path = QPainterPath()
        path.addRoundedRect(0, 0, r, r, radius, radius)
        p.setClipPath(path)

        if self._pixmap and not self._pixmap.isNull():
            x = (self._pixmap.width() - r) // 2
            y = (self._pixmap.height() - r) // 2
            p.drawPixmap(0, 0, self._pixmap, x, y, r, r)
        else:
            # gradient placeholder
            g = QLinearGradient(0, 0, r, r)
            g.setColorAt(0, QColor("#1a1a3a"))
            g.setColorAt(1, QColor("#0d0d20"))
            p.fillRect(0, 0, r, r, g)

            p.setPen(QColor("#2a2a5a"))
            p.setFont(QFont("DM Sans", 72, QFont.Bold))
            p.drawText(0, 0, r, r, Qt.AlignCenter, "♪")

        # subtle inner shadow / vignette
        grad = QRadialGradient(r / 2, r / 2, r / 2)
        grad.setColorAt(0.7, QColor(0, 0, 0, 0))
        grad.setColorAt(1.0, QColor(0, 0, 0, 80))
        p.setClipping(False)
        p.setClipPath(path)
        p.fillRect(0, 0, r, r, grad)

        p.end()


# ─────────────────────────────────────────────────────────────────
#  Queue item row
# ─────────────────────────────────────────────────────────────────
class _QueueRow(QWidget):
    double_clicked = pyqtSignal(str, dict)  # file_path, metadata

    def __init__(
        self,
        index: int,
        title: str,
        artist: str,
        duration: str,
        file_path: str,
        metadata: dict,
        is_current: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self._file_path = file_path
        self._metadata  = metadata
        self._is_current = is_current
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(48)
        self._build(index, title, artist, duration, is_current)

    def _build(self, idx, title, artist, duration, current):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(10)

        # index / playing indicator
        if current:
            num = QLabel("▶")
            num.setStyleSheet("color: #4d59fb; font-size: 11px; font-weight: 700; background: transparent;")
        else:
            num = QLabel(f"{idx + 1}")
            num.setStyleSheet("color: #3a3a60; font-size: 10px; font-weight: 600; background: transparent;")
        num.setFixedWidth(18)
        lay.addWidget(num)

        # thumbnail placeholder (small square)
        thumb = QLabel()
        thumb.setFixedSize(36, 36)
        px = QPixmap(36, 36)
        px.fill(QColor("#1a1a38"))
        p = QPainter(px)
        p.setPen(QColor("#3a3a60"))
        p.setFont(QFont("DM Sans", 14, QFont.Bold))
        p.drawText(0, 0, 36, 36, Qt.AlignCenter, "♪")
        p.end()
        thumb.setPixmap(px)
        thumb.setStyleSheet("border-radius: 6px;")
        lay.addWidget(thumb)

        # meta
        meta_w = QWidget()
        meta_w.setStyleSheet("background: transparent;")
        m = QVBoxLayout(meta_w)
        m.setContentsMargins(0, 0, 0, 0)
        m.setSpacing(2)

        t_lbl = QLabel(title)
        t_lbl.setObjectName("queue_track_title")
        fm = t_lbl.fontMetrics().elidedText(title, Qt.ElideRight, 160)
        t_lbl.setText(fm)
        if current:
            t_lbl.setStyleSheet("color: #4d59fb; font-size: 12px; font-weight: 700; background: transparent;")
        m.addWidget(t_lbl)

        a_lbl = QLabel(artist)
        a_lbl.setObjectName("queue_track_artist")
        m.addWidget(a_lbl)

        lay.addWidget(meta_w, 1)

        # duration
        dur = QLabel(duration)
        dur.setObjectName("queue_track_duration")
        lay.addWidget(dur)

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.double_clicked.emit(self._file_path, self._metadata)
        super().mouseDoubleClickEvent(e)

    def enterEvent(self, e):
        self.setStyleSheet("background-color: #141424; border-radius: 10px;")
        super().enterEvent(e)

    def leaveEvent(self, e):
        if self._is_current:
            self.setStyleSheet("background-color: #181830; border-radius: 10px;")
        else:
            self.setStyleSheet("")
        super().leaveEvent(e)


# ─────────────────────────────────────────────────────────────────
#  Main PlaybackController
# ─────────────────────────────────────────────────────────────────
class PlaybackController(QFrame):
    """Right-panel "Now Playing" widget."""

    play_pause_clicked          = pyqtSignal()
    prev_clicked                = pyqtSignal()
    next_clicked                = pyqtSignal()
    seek_requested              = pyqtSignal(int)    # ms
    volume_changed              = pyqtSignal(int)    # 0-100
    shuffle_toggled             = pyqtSignal(bool)
    repeat_toggled              = pyqtSignal(bool)
    queue_item_double_clicked   = pyqtSignal(str, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("now_playing_panel")
        self.setFixedWidth(310)

        self._is_playing    = False
        self._shuffle_on    = False
        self._repeat_on     = False
        self._duration_ms   = 0
        self._current_ms    = 0
        self._seeking       = False

        # queue data: list of (file_path, metadata)
        self._queue: List[Tuple[str, Dict]] = []
        self._current_idx = -1

        self._build_ui()

        # progress ticker
        self._ticker = QTimer(self)
        self._ticker.setInterval(500)
        self._ticker.timeout.connect(self._tick_progress)

    # ── build ──────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 20, 18, 16)
        root.setSpacing(0)

        # "Now Playing" tiny header
        np_lbl = QLabel("NOW PLAYING")
        np_lbl.setObjectName("np_label_small")
        root.addWidget(np_lbl)
        root.addSpacing(14)

        # album art
        self._art = _AlbumArtWidget()
        root.addWidget(self._art, 0, Qt.AlignHCenter)
        root.addSpacing(18)

        # track title + artist
        self._title_lbl = QLabel("No track playing")
        self._title_lbl.setObjectName("np_track_title")
        self._title_lbl.setWordWrap(False)
        self._title_lbl.setAlignment(Qt.AlignCenter)
        root.addWidget(self._title_lbl)
        root.addSpacing(4)

        self._artist_lbl = QLabel("—")
        self._artist_lbl.setObjectName("np_artist_name")
        self._artist_lbl.setAlignment(Qt.AlignCenter)
        root.addWidget(self._artist_lbl)
        root.addSpacing(16)

        # ── progress ──
        prog_container = QWidget()
        prog_container.setStyleSheet("background: transparent;")
        pl = QVBoxLayout(prog_container)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(4)

        self._progress = QSlider(Qt.Horizontal)
        self._progress.setObjectName("np_progress")
        self._progress.setRange(0, 1000)
        self._progress.setValue(0)
        self._progress.setFixedHeight(18)
        self._progress.sliderPressed.connect(self._on_seek_start)
        self._progress.sliderReleased.connect(self._on_seek_end)
        pl.addWidget(self._progress)

        time_row = QHBoxLayout()
        self._elapsed_lbl = QLabel("0:00")
        self._elapsed_lbl.setObjectName("np_time_label")
        self._remain_lbl  = QLabel("0:00")
        self._remain_lbl.setObjectName("np_time_label")
        time_row.addWidget(self._elapsed_lbl)
        time_row.addStretch()
        time_row.addWidget(self._remain_lbl)
        pl.addLayout(time_row)

        root.addWidget(prog_container)
        root.addSpacing(14)

        # ── playback controls ──
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(4)
        ctrl_row.setContentsMargins(0, 0, 0, 0)
        ctrl_row.addStretch()

        self._shuffle_btn = self._mk_ctrl("⇄", "Shuffle")
        self._shuffle_btn.clicked.connect(self._on_shuffle)
        ctrl_row.addWidget(self._shuffle_btn)

        self._prev_btn = self._mk_ctrl("⏮", "Previous")
        self._prev_btn.clicked.connect(self.prev_clicked)
        ctrl_row.addWidget(self._prev_btn)

        self._play_btn = QPushButton("▶")
        self._play_btn.setObjectName("play_pause_btn")
        self._play_btn.setFixedSize(56, 56)
        self._play_btn.setToolTip("Play / Pause")
        self._play_btn.clicked.connect(self._on_play_pause)
        ctrl_row.addWidget(self._play_btn)

        self._next_btn = self._mk_ctrl("⏭", "Next")
        self._next_btn.clicked.connect(self.next_clicked)
        ctrl_row.addWidget(self._next_btn)

        self._repeat_btn = self._mk_ctrl("↻", "Repeat")
        self._repeat_btn.clicked.connect(self._on_repeat)
        ctrl_row.addWidget(self._repeat_btn)

        ctrl_row.addStretch()
        root.addLayout(ctrl_row)
        root.addSpacing(14)

        # ── volume ──
        vol_row = QHBoxLayout()
        vol_row.setContentsMargins(0, 0, 0, 0)
        vol_row.setSpacing(8)

        vol_icon = QLabel("🔊")
        vol_icon.setStyleSheet("color: #4a4a65; font-size: 14px; background: transparent;")
        vol_row.addWidget(vol_icon)

        self._vol_slider = QSlider(Qt.Horizontal)
        self._vol_slider.setObjectName("vol_slider")
        self._vol_slider.setRange(0, 100)
        self._vol_slider.setValue(70)
        self._vol_slider.setFixedHeight(18)
        self._vol_slider.valueChanged.connect(
            lambda v: self.volume_changed.emit(v)
        )
        vol_row.addWidget(self._vol_slider)

        root.addLayout(vol_row)
        root.addSpacing(20)

        # ── divider ──
        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setStyleSheet("background-color: #141424; border: none; max-height: 1px;")
        root.addWidget(div)
        root.addSpacing(12)

        # ── queue ──
        queue_hdr = QHBoxLayout()
        qlbl = QLabel("Playlist")
        qlbl.setObjectName("queue_header")
        queue_hdr.addWidget(qlbl)
        queue_hdr.addStretch()

        clear_btn = QPushButton("Clear")
        clear_btn.setObjectName("ctrl_btn")
        clear_btn.setFixedHeight(24)
        clear_btn.setFixedWidth(50)
        clear_btn.setStyleSheet("font-size: 10px;")
        clear_btn.clicked.connect(self.clear_queue)
        queue_hdr.addWidget(clear_btn)

        root.addLayout(queue_hdr)
        root.addSpacing(8)

        # scroll area for queue
        self._queue_scroll = QScrollArea()
        self._queue_scroll.setWidgetResizable(True)
        self._queue_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._queue_scroll.setStyleSheet("background: transparent; border: none;")
        self._queue_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._queue_inner = QWidget()
        self._queue_inner.setStyleSheet("background: transparent;")
        self._queue_inner_lay = QVBoxLayout(self._queue_inner)
        self._queue_inner_lay.setContentsMargins(0, 0, 0, 0)
        self._queue_inner_lay.setSpacing(2)
        self._queue_inner_lay.addStretch()

        self._queue_scroll.setWidget(self._queue_inner)
        root.addWidget(self._queue_scroll, 1)

    # ── button factory ─────────────────────────────────────────

    @staticmethod
    def _mk_ctrl(icon: str, tip: str) -> QPushButton:
        btn = QPushButton(icon)
        btn.setObjectName("ctrl_btn")
        btn.setFixedSize(36, 36)
        btn.setToolTip(tip)
        return btn

    # ── slot handlers ──────────────────────────────────────────

    def _on_play_pause(self):
        self.play_pause_clicked.emit()

    def _on_shuffle(self):
        self._shuffle_on = not self._shuffle_on
        self._shuffle_btn.setProperty("active", str(self._shuffle_on).lower())
        self._shuffle_btn.style().unpolish(self._shuffle_btn)
        self._shuffle_btn.style().polish(self._shuffle_btn)
        self.shuffle_toggled.emit(self._shuffle_on)

    def _on_repeat(self):
        self._repeat_on = not self._repeat_on
        self._repeat_btn.setProperty("active", str(self._repeat_on).lower())
        self._repeat_btn.style().unpolish(self._repeat_btn)
        self._repeat_btn.style().polish(self._repeat_btn)
        self.repeat_toggled.emit(self._repeat_on)

    def _on_seek_start(self):
        self._seeking = True

    def _on_seek_end(self):
        if self._duration_ms > 0:
            pos = int(self._progress.value() / 1000 * self._duration_ms)
            self.seek_requested.emit(pos)
        self._seeking = False

    def _tick_progress(self):
        if not self._seeking and self._duration_ms > 0 and self._is_playing:
            self._current_ms += 500
            self._update_progress_ui()

    def _update_progress_ui(self):
        ms = min(self._current_ms, self._duration_ms)
        pct = int(ms / self._duration_ms * 1000) if self._duration_ms else 0
        self._progress.blockSignals(True)
        self._progress.setValue(pct)
        self._progress.blockSignals(False)

        elapsed = _fmt_ms(ms)
        remain  = _fmt_ms(max(0, self._duration_ms - ms))
        self._elapsed_lbl.setText(elapsed)
        self._remain_lbl.setText(f"-{remain}")

    # ── public API ─────────────────────────────────────────────

    def set_track(
        self,
        title: str,
        artist: str,
        duration_ms: int = 0,
        pixmap: Optional[QPixmap] = None,
    ) -> None:
        """Update displayed track information."""
        fm = QFontMetrics(self._title_lbl.font())
        t = fm.elidedText(title, Qt.ElideRight, 260)
        self._title_lbl.setText(t)
        self._artist_lbl.setText(artist)
        self._duration_ms  = duration_ms
        self._current_ms   = 0
        self._update_progress_ui()
        if pixmap:
            self._art.set_pixmap(pixmap)
        else:
            self._art._pixmap = None
            self._art.update()

    def set_playing(self, playing: bool) -> None:
        self._is_playing = playing
        self._play_btn.setText("⏸" if playing else "▶")
        if playing:
            self._ticker.start()
        else:
            self._ticker.stop()

    def update_position(self, position_ms: int) -> None:
        """Called by AudioPlayerWidget on positionChanged."""
        if not self._seeking:
            self._current_ms = position_ms
            self._update_progress_ui()

    def set_volume(self, volume: int) -> None:
        self._vol_slider.blockSignals(True)
        self._vol_slider.setValue(volume)
        self._vol_slider.blockSignals(False)

    # ── queue management ───────────────────────────────────────

    def set_queue(
        self,
        items: List[Tuple[str, Dict]],
        current_index: int = -1,
    ) -> None:
        self._queue = items
        self._current_idx = current_index
        self._rebuild_queue()

    def add_to_queue(self, file_path: str, metadata: dict) -> None:
        self._queue.append((file_path, metadata))
        self._rebuild_queue()

    def clear_queue(self) -> None:
        self._queue.clear()
        self._current_idx = -1
        self._rebuild_queue()

    def set_current_queue_index(self, index: int) -> None:
        self._current_idx = index
        self._rebuild_queue()

    def _rebuild_queue(self) -> None:
        # clear
        while self._queue_inner_lay.count() > 1:   # keep trailing stretch
            item = self._queue_inner_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for i, (fp, md) in enumerate(self._queue):
            title    = md.get("title",  "Unknown")
            artist   = md.get("artist", "Unknown")
            dur_s    = md.get("duration", 0) or 0
            duration = _fmt_ms(dur_s * 1000)
            current  = (i == self._current_idx)
            row = _QueueRow(i, title, artist, duration, fp, md, current)
            row.double_clicked.connect(self.queue_item_double_clicked)
            self._queue_inner_lay.insertWidget(i, row)

        # scroll to current
        if 0 <= self._current_idx < self._queue_inner_lay.count() - 1:
            w = self._queue_inner_lay.itemAt(self._current_idx).widget()
            if w:
                QTimer.singleShot(50, lambda: self._queue_scroll.ensureWidgetVisible(w))


# ─────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────
def _fmt_ms(ms: int) -> str:
    """Format milliseconds as M:SS."""
    secs = int(ms / 1000)
    m, s = divmod(secs, 60)
    return f"{m}:{s:02d}"