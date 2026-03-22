"""
Bottom now-playing bar — black background, QToolButton icons.
"""
from __future__ import annotations

import os
from typing import Optional

from PyQt5.QtCore import Qt, QTimer, QSize, pyqtSignal
from PyQt5.QtGui import QFontMetrics, QPainter, QPainterPath, QColor, QPixmap, QIcon
from PyQt5.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QSlider,
    QSizePolicy, QWidget, QToolButton,
)

from app.desktop.threads.thumbnail_loader import ThumbnailLoader

_ICONS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "assets", "icons")
)


def _icon_path(name: str) -> str:
    return os.path.join(_ICONS_DIR, name)


def _fmt_ms(ms: int) -> str:
    s = int(ms / 1000)
    m, r = divmod(s, 60)
    return f"{m}:{r:02d}"


_FONT = "Inter, 'Segoe UI', 'SF Pro Display', system-ui, sans-serif"

_ICON_BTN_BASE = (
    "QToolButton{background:transparent;border:none;padding:0;margin:0;outline:none;"
    "min-width:32px;min-height:32px;max-width:32px;max-height:32px;}"
    "QToolButton:hover{background:rgba(255,255,255,0.07);border-radius:10px;}"
    "QToolButton:pressed{background:rgba(255,255,255,0.11);border-radius:10px;}"
)


class BottomNowPlayingBar(QFrame):
    play_pause_clicked = pyqtSignal()
    prev_clicked = pyqtSignal()
    next_clicked = pyqtSignal()
    shuffle_clicked = pyqtSignal()
    repeat_clicked = pyqtSignal()
    seek_requested = pyqtSignal(int)
    volume_changed = pyqtSignal(int)
    mute_toggle_requested = pyqtSignal()

    _ART = 54
    _PLAY_SIZE = 56
    _PLAY_ICON = 28
    _BTN_ICON = 20

    # Pełny czarny pas — bez obramowania / cienia
    _CARD_STYLE = (
        "QFrame#bottom_player_card{"
        "background:#000000;"
        "border:none;"
        "border-radius:0px;"
        f"font-family:{_FONT};"
        "}"
    )

    _PROGRESS_SLIDER_STYLE = (
        "QSlider::groove:horizontal{height:3px;background:rgba(255,255,255,0.16);"
        "border-radius:2px;}"
        "QSlider::sub-page:horizontal{background:#ffffff;border-radius:2px;}"
        "QSlider::add-page:horizontal{background:transparent;}"
        "QSlider::handle:horizontal{width:10px;height:10px;margin:-4px 0;"
        "background:#ffffff;border-radius:5px;border:none;}"
    )

    _VOL_SLIDER_STYLE = (
        "QSlider::groove:horizontal{height:3px;background:rgba(255,255,255,0.14);"
        "border-radius:2px;}"
        "QSlider::sub-page:horizontal{background:rgba(255,255,255,0.45);border-radius:2px;}"
        "QSlider::handle:horizontal{width:8px;height:8px;margin:-3px 0;"
        "background:#f0f0f5;border-radius:4px;border:none;}"
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("bottom_player_outer")
        self.setStyleSheet("QFrame#bottom_player_outer{background:#000000;border:none;}")
        self._is_playing = False
        self._duration_ms = 0
        self._current_ms = 0
        self._seeking = False
        self._thumb_loader: Optional[ThumbnailLoader] = None
        self._muted = False

        self._icon_play = QIcon(_icon_path("play.png"))
        self._icon_pause = QIcon(_icon_path("pause.png"))

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._card = QFrame()
        self._card.setObjectName("bottom_player_card")
        self._card.setStyleSheet(self._CARD_STYLE)

        inner = QVBoxLayout(self._card)
        inner.setContentsMargins(18, 12, 18, 12)
        inner.setSpacing(10)

        # Left: art + meta
        left = QHBoxLayout()
        left.setSpacing(12)
        self._art = QLabel()
        self._art.setFixedSize(self._ART, self._ART)
        self._art.setScaledContents(False)
        self._clear_art()
        left.addWidget(self._art)

        meta = QVBoxLayout()
        meta.setSpacing(2)
        self._title_lbl = QLabel("")
        self._title_lbl.setStyleSheet(
            "color:#fafafa;font-size:13px;font-weight:700;letter-spacing:-0.2px;")
        self._artist_lbl = QLabel("")
        self._artist_lbl.setStyleSheet(
            "color:#8e8e9e;font-size:12px;font-weight:500;")
        meta.addWidget(self._title_lbl)
        meta.addWidget(self._artist_lbl)
        meta.addStretch()
        w_meta = QWidget()
        w_meta.setLayout(meta)
        w_meta.setMinimumWidth(160)
        left.addWidget(w_meta, 1)

        # Center: transport
        ctr = QHBoxLayout()
        ctr.setSpacing(10)
        ctr.setContentsMargins(0, 0, 0, 0)
        ctr.setAlignment(Qt.AlignCenter)
        self._shuffle_btn = self._png_btn("shuffle.png", "Shuffle", self._BTN_ICON)
        self._shuffle_btn.clicked.connect(self.shuffle_clicked.emit)
        ctr.addWidget(self._shuffle_btn, alignment=Qt.AlignCenter)

        self._prev_btn = self._png_btn("prev.png", "Previous", self._BTN_ICON)
        self._prev_btn.clicked.connect(self.prev_clicked.emit)
        ctr.addWidget(self._prev_btn, alignment=Qt.AlignCenter)

        self._play_btn = QToolButton()
        self._play_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self._play_btn.setCursor(Qt.PointingHandCursor)
        self._play_btn.setFixedSize(self._PLAY_SIZE, self._PLAY_SIZE)
        self._play_btn.setIcon(self._icon_play)
        self._play_btn.setIconSize(QSize(self._PLAY_ICON, self._PLAY_ICON))
        self._apply_play_style(False)
        self._play_btn.clicked.connect(self.play_pause_clicked.emit)
        ctr.addWidget(self._play_btn, alignment=Qt.AlignCenter)

        self._next_btn = self._png_btn("next.png", "Next", self._BTN_ICON)
        self._next_btn.clicked.connect(self.next_clicked.emit)
        ctr.addWidget(self._next_btn, alignment=Qt.AlignCenter)

        self._repeat_btn = self._png_btn("loop.png", "Repeat", self._BTN_ICON)
        self._repeat_btn.clicked.connect(self.repeat_clicked.emit)
        ctr.addWidget(self._repeat_btn, alignment=Qt.AlignCenter)

        ctr_outer = QWidget()
        ctr_col = QVBoxLayout(ctr_outer)
        ctr_col.setContentsMargins(0, 0, 0, 0)
        ctr_col.setSpacing(0)
        ctr_col.addStretch(1)
        ctr_row = QHBoxLayout()
        ctr_row.setContentsMargins(0, 0, 0, 0)
        ctr_row.addStretch(1)
        ctr_row.addLayout(ctr)
        ctr_row.addStretch(1)
        ctr_col.addLayout(ctr_row)
        ctr_col.addStretch(1)

        # Right: tylko głośność (wyrównanie do prawej krawędzi karty)
        util = QHBoxLayout()
        util.setSpacing(8)
        util.setContentsMargins(0, 0, 0, 0)
        util.setAlignment(Qt.AlignVCenter | Qt.AlignRight)

        self._vol_icon_btn = self._png_btn("volume.png", "Mute / unmute", self._BTN_ICON)
        self._vol_icon_btn.clicked.connect(self.mute_toggle_requested.emit)
        util.addWidget(self._vol_icon_btn, alignment=Qt.AlignCenter)

        self._vol_slider = QSlider(Qt.Horizontal)
        self._vol_slider.setRange(0, 100)
        self._vol_slider.setValue(70)
        self._vol_slider.setFixedWidth(120)
        self._vol_slider.setFixedHeight(18)
        self._vol_slider.valueChanged.connect(self.volume_changed.emit)
        self._vol_slider.setStyleSheet(self._VOL_SLIDER_STYLE)
        util.addWidget(self._vol_slider, alignment=Qt.AlignVCenter)

        util_outer = QWidget()
        util_col = QVBoxLayout(util_outer)
        util_col.setContentsMargins(0, 0, 0, 0)
        util_col.setSpacing(0)
        util_col.addStretch(1)
        util_row = QHBoxLayout()
        util_row.setContentsMargins(0, 0, 0, 0)
        util_row.addStretch(1)
        util_row.addLayout(util)
        util_col.addLayout(util_row)
        util_col.addStretch(1)

        left_wrap = QWidget()
        left_wrap.setLayout(left)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.addWidget(left_wrap, 0, 0, alignment=Qt.AlignLeft | Qt.AlignVCenter)
        grid.addWidget(ctr_outer, 0, 1, alignment=Qt.AlignHCenter | Qt.AlignVCenter)
        grid.addWidget(util_outer, 0, 2, alignment=Qt.AlignRight | Qt.AlignVCenter)
        grid.setColumnStretch(0, 1)
        grid.setColumnMinimumWidth(1, 280)
        grid.setColumnStretch(2, 1)
        inner.addLayout(grid)

        # Progress row
        prog_row = QHBoxLayout()
        prog_row.setSpacing(12)
        self._elapsed_lbl = QLabel("0:00")
        self._elapsed_lbl.setStyleSheet(
            "color:#8b8b9a;font-size:11px;font-weight:600;min-width:36px;")
        self._elapsed_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._progress = QSlider(Qt.Horizontal)
        self._progress.setRange(0, 1000)
        self._progress.setFixedHeight(14)
        self._progress.setStyleSheet(self._PROGRESS_SLIDER_STYLE)
        self._progress.sliderPressed.connect(self._on_seek_start)
        self._progress.sliderReleased.connect(self._on_seek_end)
        self._remain_lbl = QLabel("")
        self._remain_lbl.setStyleSheet(
            "color:#8b8b9a;font-size:11px;font-weight:600;min-width:44px;")
        self._remain_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        prog_row.addWidget(self._elapsed_lbl)
        prog_row.addWidget(self._progress, 1)
        prog_row.addWidget(self._remain_lbl)
        inner.addLayout(prog_row)

        root.addWidget(self._card)

        self.setFixedHeight(132)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._ticker = QTimer(self)
        self._ticker.setInterval(400)
        self._ticker.timeout.connect(self._tick_fake_progress)

    def _png_btn(self, filename: str, tip: str, icon_px: int) -> QToolButton:
        b = QToolButton()
        b.setToolButtonStyle(Qt.ToolButtonIconOnly)
        b.setIcon(QIcon(_icon_path(filename)))
        b.setIconSize(QSize(icon_px, icon_px))
        b.setFixedSize(32, 32)
        b.setToolTip(tip)
        b.setCursor(Qt.PointingHandCursor)
        b.setAutoRaise(True)
        b.setStyleSheet(_ICON_BTN_BASE)
        return b

    def _apply_play_style(self, playing: bool) -> None:
        self._play_btn.setIcon(self._icon_pause if playing else self._icon_play)
        r = self._PLAY_SIZE // 2
        self._play_btn.setStyleSheet(
            f"QToolButton{{background:#ffffff;border:none;outline:none;padding:0;margin:0;"
            f"min-width:{self._PLAY_SIZE}px;min-height:{self._PLAY_SIZE}px;"
            f"max-width:{self._PLAY_SIZE}px;max-height:{self._PLAY_SIZE}px;"
            f"border-radius:{r}px;}}"
            "QToolButton:hover{background:#f2f2f8;border:none;outline:none;}"
            "QToolButton:pressed{background:#e8e8ee;border:none;outline:none;}")

    def _clear_art(self) -> None:
        s = self._ART
        px = QPixmap(s, s)
        px.fill(Qt.transparent)
        p = QPainter(px)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, s, s, 10, 10)
        p.setClipPath(path)
        p.fillRect(0, 0, s, s, QColor("#1a1a1a"))
        p.end()
        self._art.setPixmap(px)

    def _on_seek_start(self):
        self._seeking = True

    def _on_seek_end(self):
        if self._duration_ms > 0:
            pos = int(self._progress.value() / 1000 * self._duration_ms)
            self.seek_requested.emit(pos)
        self._seeking = False

    def _tick_fake_progress(self):
        if not self._seeking and self._duration_ms > 0 and self._is_playing:
            self._current_ms = min(self._current_ms + 400, self._duration_ms)
            self._refresh_progress_only()

    def _refresh_progress_only(self):
        ms = min(self._current_ms, self._duration_ms)
        pct = int(ms / self._duration_ms * 1000) if self._duration_ms else 0
        self._progress.blockSignals(True)
        self._progress.setValue(pct)
        self._progress.blockSignals(False)
        self._elapsed_lbl.setText(_fmt_ms(ms))
        if self._duration_ms > 0:
            rem = max(0, self._duration_ms - ms)
            self._remain_lbl.setText(f"-{_fmt_ms(rem)}")
        else:
            self._remain_lbl.setText("")

    def set_track(
        self,
        title: str,
        artist: str,
        duration_ms: int = 0,
        cover_url: str = "",
        pixmap: Optional[QPixmap] = None,
    ) -> None:
        fm = QFontMetrics(self._title_lbl.font())
        mw = max(160, min(320, self.width() // 3))
        self._title_lbl.setText(fm.elidedText(title or "", Qt.ElideRight, mw))
        self._artist_lbl.setText(fm.elidedText(artist or "", Qt.ElideRight, mw))
        self._duration_ms = max(0, int(duration_ms))
        self._current_ms = 0
        self._refresh_progress_only()
        self._cleanup_thumb()
        if pixmap and not pixmap.isNull():
            self._apply_art(pixmap)
        elif cover_url and cover_url.startswith("http"):
            try:
                self._thumb_loader = ThumbnailLoader(cover_url)
                self._thumb_loader.loaded.connect(self._on_art_loaded)
                self._thumb_loader.finished.connect(self._cleanup_thumb)
                self._thumb_loader.start()
            except Exception:
                self._clear_art()
        else:
            self._clear_art()

    def _apply_art(self, pixmap: QPixmap) -> None:
        s = self._ART
        sc = pixmap.scaled(s, s, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        out = QPixmap(s, s)
        out.fill(Qt.transparent)
        p = QPainter(out)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, s, s, 10, 10)
        p.setClipPath(path)
        x = (sc.width() - s) // 2
        y = (sc.height() - s) // 2
        p.drawPixmap(-x, -y, sc)
        p.end()
        self._art.setPixmap(out)

    def _on_art_loaded(self, px: QPixmap) -> None:
        if not px.isNull():
            self._apply_art(px)

    def _cleanup_thumb(self) -> None:
        if self._thumb_loader:
            try:
                self._thumb_loader.loaded.disconnect()
                self._thumb_loader.finished.disconnect()
            except Exception:
                pass
            self._thumb_loader = None

    def set_playing(self, playing: bool) -> None:
        self._is_playing = playing
        self._apply_play_style(playing)
        if playing:
            self._ticker.start()
        else:
            self._ticker.stop()

    def update_position(self, position_ms: int) -> None:
        if not self._seeking:
            self._current_ms = position_ms
            self._refresh_progress_only()

    def set_duration_ms(self, ms: int) -> None:
        self._duration_ms = max(0, int(ms))
        self._refresh_progress_only()

    def set_volume_ui(
        self,
        value: int,
        muted: bool = False,
        nominal_when_muted: Optional[int] = None,
    ) -> None:
        self._muted = muted
        self._vol_slider.blockSignals(True)
        if muted:
            if nominal_when_muted is not None:
                display_v = max(0, min(100, int(nominal_when_muted)))
            else:
                display_v = max(0, min(100, int(value)))
            self._vol_slider.setValue(display_v)
            self._vol_slider.setEnabled(False)
        else:
            self._vol_slider.setEnabled(True)
            self._vol_slider.setValue(max(0, min(100, int(value))))
        self._vol_slider.blockSignals(False)
        self._vol_icon_btn.setIcon(QIcon(_icon_path("mute.png" if muted else "volume.png")))
        self._vol_icon_btn.setToolTip("Unmute" if muted else "Mute")
        self._vol_slider.setToolTip(
            "Wyciszone — kliknij ikonę głośnika, by przywrócić głośność"
            if muted else f"Głośność: {self._vol_slider.value()}%")

    def set_shuffle_style(self, active: bool) -> None:
        # Tylko off / on — jeden styl aktywny, jeden nieaktywny
        self._shuffle_btn.setToolTip(
            "Shuffle: włączony" if active else "Shuffle: wyłączony")
        if active:
            self._shuffle_btn.setStyleSheet(
                "QToolButton{background:rgba(255,255,255,0.10);border:none;outline:none;padding:0;margin:0;"
                "border-radius:10px;min-width:32px;min-height:32px;max-width:32px;max-height:32px;}"
                "QToolButton:hover{background:rgba(255,255,255,0.14);border-radius:10px;}"
                "QToolButton:pressed{background:rgba(255,255,255,0.11);border-radius:10px;}")
        else:
            self._shuffle_btn.setStyleSheet(_ICON_BTN_BASE)

    def set_repeat_style(self, mode: int) -> None:
        name = "loop.png" if mode == 0 else "loop_active.png"
        self._repeat_btn.setIcon(QIcon(_icon_path(name)))
        tip = "Repeat: off"
        if mode == 1:
            tip = "Repeat: all"
        elif mode == 2:
            tip = "Repeat: one"
        self._repeat_btn.setToolTip(tip)
