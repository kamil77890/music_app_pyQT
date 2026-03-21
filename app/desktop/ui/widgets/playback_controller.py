"""
PlaybackController  (Now Playing Panel — Right Sidebar)

Layout:
  ┌──────────────────────────────┐
  │  NOW PLAYING                 │
  │  [Album Art]                 │
  │  Title / Artist              │
  │  Progress / Controls / Vol   │
  ├──────────────────────────────┤
  │  Queue OR Album Browse       │  ← bottom section toggles
  └──────────────────────────────┘

Album browse: track rows with covers, no numbers, hover border,
download button on the right. "Download All" button at top.
"""

from __future__ import annotations

from typing import Optional, List, Tuple, Dict

from PyQt5.QtCore import (
    Qt, QTimer, pyqtSignal, QPropertyAnimation, QEasingCurve,
)
from PyQt5.QtGui import (
    QPainter, QPainterPath, QColor, QPixmap, QLinearGradient,
    QPen, QFont, QFontMetrics, QRadialGradient,
)
from PyQt5.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSlider, QScrollArea, QSizePolicy, QStackedWidget,
)


# ─────────────────────────────────────────────────────────────────
#  Album art (rounded square)
# ─────────────────────────────────────────────────────────────────
class _AlbumArtWidget(QWidget):
    SIZE = 220

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.SIZE, self.SIZE)
        self._pixmap: Optional[QPixmap] = None

    def set_pixmap(self, px: QPixmap) -> None:
        self._pixmap = px.scaled(
            self.SIZE, self.SIZE,
            Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        r = self.SIZE
        path = QPainterPath()
        path.addRoundedRect(0, 0, r, r, 20, 20)
        p.setClipPath(path)

        if self._pixmap and not self._pixmap.isNull():
            x = (self._pixmap.width()  - r) // 2
            y = (self._pixmap.height() - r) // 2
            p.drawPixmap(0, 0, self._pixmap, x, y, r, r)
        else:
            g = QLinearGradient(0, 0, r, r)
            g.setColorAt(0, QColor("#1a1a3a"))
            g.setColorAt(1, QColor("#0d0d20"))
            p.fillRect(0, 0, r, r, g)
            p.setPen(QColor("#2a2a5a"))
            p.setFont(QFont("DM Sans", 72, QFont.Bold))
            p.drawText(0, 0, r, r, Qt.AlignCenter, "♪")

        grad = QRadialGradient(r / 2, r / 2, r / 2)
        grad.setColorAt(0.7, QColor(0, 0, 0, 0))
        grad.setColorAt(1.0, QColor(0, 0, 0, 80))
        p.setClipping(False)
        p.setClipPath(path)
        p.fillRect(0, 0, r, r, grad)
        p.end()


# ─────────────────────────────────────────────────────────────────
#  Queue thumbnail
# ─────────────────────────────────────────────────────────────────
class _QueueThumb(QLabel):
    SIZE = 36

    def __init__(self, metadata: dict, is_current: bool = False, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.SIZE, self.SIZE)
        self._is_current = is_current
        self._loader = None
        self._draw_placeholder()

        url = metadata.get("thumbnail") or metadata.get("cover") or ""
        if url and url.startswith("http"):
            self._load_url(url)

    def _draw_placeholder(self):
        s = self.SIZE
        px = QPixmap(s, s)
        color = QColor("#4d59fb") if self._is_current else QColor("#1a1a38")
        px.fill(color)
        p = QPainter(px)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, s, s, 7, 7)
        p.setClipPath(path)
        p.fillRect(0, 0, s, s, color)
        p.setPen(QPen(QColor("#ffffff") if self._is_current else QColor("#4a4a65")))
        p.setFont(QFont("Arial", 11, QFont.Bold))
        p.drawText(0, 0, s, s, Qt.AlignCenter,
                   "▶" if self._is_current else "♪")
        p.end()
        self.setPixmap(px)
        self.setStyleSheet("border-radius: 7px;")

    def _load_url(self, url: str):
        try:
            from app.desktop.threads.thumbnail_loader import ThumbnailLoader
            self._loader = ThumbnailLoader(url)
            self._loader.loaded.connect(self._set_image)
            self._loader.finished.connect(self._cleanup_loader)
            self._loader.start()
        except Exception:
            pass

    def _set_image(self, pixmap: QPixmap):
        if pixmap.isNull():
            return
        s = self.SIZE
        scaled = pixmap.scaled(s, s, Qt.KeepAspectRatioByExpanding,
                               Qt.SmoothTransformation)
        result = QPixmap(s, s)
        result.fill(Qt.transparent)
        p = QPainter(result)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, s, s, 7, 7)
        p.setClipPath(path)
        x = (scaled.width()  - s) // 2
        y = (scaled.height() - s) // 2
        p.drawPixmap(-x, -y, scaled)
        if self._is_current:
            p.fillRect(0, 0, s, s, QColor(0, 0, 0, 110))
            p.setPen(QPen(QColor("#ffffff")))
            p.setFont(QFont("Arial", 9, QFont.Bold))
            p.drawText(0, 0, s, s, Qt.AlignCenter, "▶")
        p.end()
        self.setPixmap(result)

    def _cleanup_loader(self):
        if self._loader:
            try:
                self._loader.loaded.disconnect()
                self._loader.finished.disconnect()
            except Exception:
                pass
            self._loader = None


# ─────────────────────────────────────────────────────────────────
#  Queue row
# ─────────────────────────────────────────────────────────────────
class _QueueRow(QWidget):
    double_clicked = pyqtSignal(str, dict)

    ROW_H = 60

    def __init__(
        self,
        index:     int,
        title:     str,
        artist:    str,
        duration:  str,
        file_path: str,
        metadata:  dict,
        is_current: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self._file_path = file_path
        self._metadata  = metadata
        self._is_current = is_current
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(self.ROW_H)
        self._build(index, title, artist, duration, is_current)
        self._apply_style()

    def _build(self, idx, title, artist, duration, current):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(10)

        thumb = _QueueThumb(self._metadata, is_current=current)
        lay.addWidget(thumb)

        meta_w = QWidget()
        meta_w.setStyleSheet("background: transparent;")
        m = QVBoxLayout(meta_w)
        m.setContentsMargins(0, 0, 0, 0)
        m.setSpacing(3)

        t_lbl = QLabel(title)
        t_lbl.setObjectName("queue_track_title")
        fm = t_lbl.fontMetrics().elidedText(title, Qt.ElideRight, 155)
        t_lbl.setText(fm)
        if current:
            t_lbl.setStyleSheet(
                "color:#4d59fb;font-size:12px;font-weight:700;background:transparent;")
        m.addWidget(t_lbl)

        a_lbl = QLabel(artist)
        a_lbl.setObjectName("queue_track_artist")
        m.addWidget(a_lbl)
        lay.addWidget(meta_w, 1)

        dur = QLabel(duration)
        dur.setObjectName("queue_track_duration")
        lay.addWidget(dur)

    def _apply_style(self):
        if self._is_current:
            self.setStyleSheet(
                "background-color:#111830;"
                "border:2px solid #4d59fb;"
                "border-radius:10px;"
            )
        else:
            self.setStyleSheet("border-radius:10px;")

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.double_clicked.emit(self._file_path, self._metadata)
        super().mouseDoubleClickEvent(e)

    def enterEvent(self, e):
        if not self._is_current:
            self.setStyleSheet(
                "background-color:#141424;border-radius:10px;"
                "border:1px solid #1e1e38;")
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._apply_style()
        super().leaveEvent(e)


# ─────────────────────────────────────────────────────────────────
#  Browse track row (album panel) — with cover, no number, download btn
# ─────────────────────────────────────────────────────────────────
class _BrowseTrackRow(QWidget):
    play_requested = pyqtSignal(dict)
    download_requested = pyqtSignal(dict)

    def __init__(self, index: int, track: dict, parent=None):
        super().__init__(parent)
        self._track = track
        self.setFixedHeight(60)
        self.setCursor(Qt.PointingHandCursor)

        self._base_style = (
            "background-color:#0f0f18;border:1px solid transparent;"
            "border-radius:10px;"
        )
        self._hover_style = (
            "background-color:#141424;border:1px solid #4d59fb;"
            "border-radius:10px;"
        )
        self.setStyleSheet(self._base_style)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(10)

        self._thumb = _QueueThumb(track, is_current=False)
        lay.addWidget(self._thumb)

        meta = QWidget()
        meta.setStyleSheet("background:transparent;")
        ml = QVBoxLayout(meta)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(2)

        title_txt = track.get("title", f"Track {index + 1}")
        t_lbl = QLabel(title_txt)
        t_lbl.setStyleSheet(
            "color:#e8eaf0;font-size:12px;font-weight:700;background:transparent;")
        t_lbl.setText(t_lbl.fontMetrics().elidedText(title_txt, Qt.ElideRight, 140))
        ml.addWidget(t_lbl)

        artist = track.get("artist", "")
        if artist:
            a_lbl = QLabel(artist)
            a_lbl.setStyleSheet(
                "color:#4a4a65;font-size:10px;background:transparent;")
            ml.addWidget(a_lbl)

        lay.addWidget(meta, 1)

        dur = track.get("duration", "")
        if dur:
            d_lbl = QLabel(str(dur))
            d_lbl.setStyleSheet(
                "color:#3a3a55;font-size:10px;background:transparent;min-width:36px;")
            d_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            lay.addWidget(d_lbl)

        self._dl_btn = QPushButton("⬇")
        self._dl_btn.setFixedSize(28, 28)
        self._dl_btn.setStyleSheet(
            "QPushButton{background:#1e1e38;border:none;border-radius:14px;"
            "color:#9395a5;font-size:12px;font-weight:700;}"
            "QPushButton:hover{background:#4d59fb;color:white;}")
        self._dl_btn.setVisible(False)
        self._dl_btn.clicked.connect(lambda: self.download_requested.emit(self._track))
        lay.addWidget(self._dl_btn)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.play_requested.emit(self._track)
        super().mousePressEvent(e)

    def enterEvent(self, e):
        self._dl_btn.setVisible(True)
        self.setStyleSheet(self._hover_style)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._dl_btn.setVisible(False)
        self.setStyleSheet(self._base_style)
        super().leaveEvent(e)


# ─────────────────────────────────────────────────────────────────
#  PlaybackController
# ─────────────────────────────────────────────────────────────────
class PlaybackController(QFrame):
    """Right panel — Now Playing at top, Queue/Album Browse toggles at bottom."""

    play_pause_clicked          = pyqtSignal()
    prev_clicked                = pyqtSignal()
    next_clicked                = pyqtSignal()
    seek_requested              = pyqtSignal(int)
    volume_changed              = pyqtSignal(int)
    shuffle_toggled             = pyqtSignal(bool)
    repeat_toggled              = pyqtSignal(bool)
    queue_item_double_clicked   = pyqtSignal(str, dict)
    browse_track_play_requested = pyqtSignal(str, dict)
    browse_track_download_requested = pyqtSignal(dict)
    download_all_album_requested = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("now_playing_panel")
        self.setFixedWidth(310)

        self._is_playing  = False
        self._shuffle_on  = False
        self._repeat_on   = False
        self._duration_ms = 0
        self._current_ms  = 0
        self._seeking     = False

        self._queue:       List[Tuple[str, Dict]] = []
        self._current_idx = -1
        self._browse_tracks: List[Dict] = []

        self._build_ui()

        self._ticker = QTimer(self)
        self._ticker.setInterval(500)
        self._ticker.timeout.connect(self._tick_progress)

    # ── build ──────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_now_playing_section())

        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setStyleSheet("background-color:#141424;border:none;max-height:1px;")
        root.addWidget(div)

        self._bottom_stack = QStackedWidget()
        self._bottom_stack.addWidget(self._build_queue_section())
        self._bottom_stack.addWidget(self._build_browse_section())
        self._bottom_stack.setCurrentIndex(0)
        root.addWidget(self._bottom_stack, 1)

    # ── Now Playing section (top) ──────────────────────────────

    def _build_now_playing_section(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background:transparent;")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(20, 24, 20, 12)
        lay.setSpacing(0)

        np_lbl = QLabel("NOW PLAYING")
        np_lbl.setObjectName("np_label_small")
        lay.addWidget(np_lbl)
        lay.addSpacing(14)

        self._art = _AlbumArtWidget()
        lay.addWidget(self._art, 0, Qt.AlignHCenter)
        lay.addSpacing(16)

        self._title_lbl = QLabel("No track playing")
        self._title_lbl.setObjectName("np_track_title")
        self._title_lbl.setWordWrap(False)
        self._title_lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._title_lbl)
        lay.addSpacing(4)

        self._artist_lbl = QLabel("—")
        self._artist_lbl.setObjectName("np_artist_name")
        self._artist_lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._artist_lbl)
        lay.addSpacing(14)

        prog_w = QWidget()
        prog_w.setStyleSheet("background:transparent;")
        pl = QVBoxLayout(prog_w)
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

        lay.addWidget(prog_w)
        lay.addSpacing(12)

        ctrl = QHBoxLayout()
        ctrl.setSpacing(4)
        ctrl.addStretch()

        self._shuffle_btn = self._mk_ctrl("⇄", "Shuffle")
        self._shuffle_btn.clicked.connect(self._on_shuffle)
        ctrl.addWidget(self._shuffle_btn)

        self._prev_btn = self._mk_ctrl("⏮", "Previous")
        self._prev_btn.clicked.connect(self.prev_clicked)
        ctrl.addWidget(self._prev_btn)

        self._play_btn = QPushButton("▶")
        self._play_btn.setObjectName("play_pause_btn")
        self._play_btn.setFixedSize(56, 56)
        self._play_btn.clicked.connect(self._on_play_pause)
        ctrl.addWidget(self._play_btn)

        self._next_btn = self._mk_ctrl("⏭", "Next")
        self._next_btn.clicked.connect(self.next_clicked)
        ctrl.addWidget(self._next_btn)

        self._repeat_btn = self._mk_ctrl("↻", "Repeat")
        self._repeat_btn.clicked.connect(self._on_repeat)
        ctrl.addWidget(self._repeat_btn)

        ctrl.addStretch()
        lay.addLayout(ctrl)
        lay.addSpacing(12)

        vol_row = QHBoxLayout()
        vol_row.setSpacing(8)
        vol_icon = QLabel("🔊")
        vol_icon.setStyleSheet(
            "color:#4a4a65;font-size:14px;background:transparent;")
        vol_row.addWidget(vol_icon)

        self._vol_slider = QSlider(Qt.Horizontal)
        self._vol_slider.setObjectName("vol_slider")
        self._vol_slider.setRange(0, 100)
        self._vol_slider.setValue(70)
        self._vol_slider.setFixedHeight(18)
        self._vol_slider.valueChanged.connect(lambda v: self.volume_changed.emit(v))
        vol_row.addWidget(self._vol_slider)
        lay.addLayout(vol_row)

        return page

    # ── Queue section (bottom page 0) ─────────────────────────

    def _build_queue_section(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background:transparent;")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(20, 12, 20, 12)
        lay.setSpacing(8)

        q_hdr = QHBoxLayout()
        qlbl = QLabel("Playlist")
        qlbl.setObjectName("queue_header")
        q_hdr.addWidget(qlbl)
        q_hdr.addStretch()
        clear_btn = QPushButton("Clear")
        clear_btn.setObjectName("ctrl_btn")
        clear_btn.setFixedHeight(24)
        clear_btn.setFixedWidth(50)
        clear_btn.setStyleSheet("font-size:10px;")
        clear_btn.clicked.connect(self.clear_queue)
        q_hdr.addWidget(clear_btn)
        lay.addLayout(q_hdr)

        self._queue_scroll = QScrollArea()
        self._queue_scroll.setWidgetResizable(True)
        self._queue_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._queue_scroll.setStyleSheet("background:transparent;border:none;")
        self._queue_scroll.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._queue_inner = QWidget()
        self._queue_inner.setStyleSheet("background:transparent;")
        self._queue_inner_lay = QVBoxLayout(self._queue_inner)
        self._queue_inner_lay.setContentsMargins(0, 0, 0, 0)
        self._queue_inner_lay.setSpacing(4)
        self._queue_inner_lay.addStretch()

        self._queue_scroll.setWidget(self._queue_inner)
        lay.addWidget(self._queue_scroll, 1)

        return page

    # ── Album Browse section (bottom page 1) ──────────────────

    def _build_browse_section(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background:transparent;")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(14, 12, 14, 8)
        lay.setSpacing(0)

        hdr_row = QHBoxLayout()
        back_btn = QPushButton("← Queue")
        back_btn.setStyleSheet(
            "QPushButton{background:transparent;border:none;color:#4d59fb;"
            "font-size:11px;font-weight:700;padding:0;text-align:left;"
            "min-height:24px;max-height:24px;}"
            "QPushButton:hover{color:#7a86ff;}")
        back_btn.setFixedHeight(24)
        back_btn.clicked.connect(self.show_now_playing_mode)
        hdr_row.addWidget(back_btn)
        hdr_row.addStretch()
        self._browse_mode_lbl = QLabel("ALBUM")
        self._browse_mode_lbl.setObjectName("np_label_small")
        hdr_row.addWidget(self._browse_mode_lbl)
        lay.addLayout(hdr_row)
        lay.addSpacing(8)

        self._browse_title_lbl = QLabel("")
        self._browse_title_lbl.setAlignment(Qt.AlignLeft)
        self._browse_title_lbl.setWordWrap(True)
        self._browse_title_lbl.setStyleSheet(
            "color:#ffffff;font-size:14px;font-weight:800;background:transparent;")
        lay.addWidget(self._browse_title_lbl)
        lay.addSpacing(2)

        self._browse_count_lbl = QLabel("")
        self._browse_count_lbl.setObjectName("np_artist_name")
        self._browse_count_lbl.setAlignment(Qt.AlignLeft)
        lay.addWidget(self._browse_count_lbl)
        lay.addSpacing(6)

        self._dl_all_browse_btn = QPushButton("⬇  Download All")
        self._dl_all_browse_btn.setFixedHeight(32)
        self._dl_all_browse_btn.setStyleSheet(
            "QPushButton{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #4d59fb,stop:1 #6c3aef);border:none;border-radius:8px;"
            "color:#fff;font-size:11px;font-weight:700;padding:0 14px;"
            "min-height:32px;max-height:32px;}"
            "QPushButton:hover{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #5e6aff,stop:1 #7a4aff);}")
        self._dl_all_browse_btn.clicked.connect(self._on_download_all_browse)
        lay.addWidget(self._dl_all_browse_btn)
        lay.addSpacing(8)

        self._browse_loading_lbl = QLabel("Loading tracks…")
        self._browse_loading_lbl.setObjectName("empty_state")
        self._browse_loading_lbl.setAlignment(Qt.AlignCenter)
        self._browse_loading_lbl.setVisible(False)
        lay.addWidget(self._browse_loading_lbl)

        self._browse_scroll = QScrollArea()
        self._browse_scroll.setWidgetResizable(True)
        self._browse_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._browse_scroll.setFrameShape(QFrame.NoFrame)
        self._browse_scroll.setStyleSheet("background:transparent;border:none;")
        self._browse_scroll.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._browse_inner = QWidget()
        self._browse_inner.setStyleSheet("background:transparent;")
        self._browse_inner_lay = QVBoxLayout(self._browse_inner)
        self._browse_inner_lay.setContentsMargins(0, 0, 0, 0)
        self._browse_inner_lay.setSpacing(4)
        self._browse_inner_lay.addStretch()

        self._browse_scroll.setWidget(self._browse_inner)
        lay.addWidget(self._browse_scroll, 1)

        return page

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
        ms  = min(self._current_ms, self._duration_ms)
        pct = int(ms / self._duration_ms * 1000) if self._duration_ms else 0
        self._progress.blockSignals(True)
        self._progress.setValue(pct)
        self._progress.blockSignals(False)
        self._elapsed_lbl.setText(_fmt_ms(ms))
        self._remain_lbl.setText(f"-{_fmt_ms(max(0, self._duration_ms - ms))}")

    # ── public: mode switching ─────────────────────────────────

    def show_now_playing_mode(self) -> None:
        self._bottom_stack.setCurrentIndex(0)

    def show_album_browse_loading(self) -> None:
        self._browse_title_lbl.setText("Loading…")
        self._browse_count_lbl.setText("")
        self._browse_loading_lbl.setVisible(True)
        self._browse_scroll.setVisible(False)
        self._dl_all_browse_btn.setVisible(False)
        self._clear_browse_list()
        self._bottom_stack.setCurrentIndex(1)

    def show_album_browse(self, playlist_id: str, tracks: List[Dict]) -> None:
        self._browse_loading_lbl.setVisible(False)
        self._browse_scroll.setVisible(True)
        self._dl_all_browse_btn.setVisible(True)
        self._browse_tracks = list(tracks)

        album_title = ""
        if tracks:
            album_title = (tracks[0].get("album") or
                           tracks[0].get("playlist_title") or "")
        if not album_title:
            album_title = "Album"

        self._browse_title_lbl.setText(album_title)
        self._browse_count_lbl.setText(
            f"{len(tracks)} track{'s' if len(tracks) != 1 else ''}")

        self._clear_browse_list()
        for i, track in enumerate(tracks):
            row = _BrowseTrackRow(i, track)
            row.play_requested.connect(self._on_browse_track)
            row.download_requested.connect(
                lambda t: self.browse_track_download_requested.emit(t))
            self._browse_inner_lay.insertWidget(i, row)

        self._bottom_stack.setCurrentIndex(1)

    def _clear_browse_list(self):
        while self._browse_inner_lay.count() > 1:
            item = self._browse_inner_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _on_browse_track(self, track: dict):
        file_path = track.get("file_path", "") or track.get("url", "")
        self.browse_track_play_requested.emit(file_path, track)

    def _on_download_all_browse(self):
        if self._browse_tracks:
            self.download_all_album_requested.emit(list(self._browse_tracks))

    # ── public: now playing ────────────────────────────────────

    def set_track(
        self,
        title:       str,
        artist:      str,
        duration_ms: int = 0,
        pixmap:      Optional[QPixmap] = None,
    ) -> None:
        fm = QFontMetrics(self._title_lbl.font())
        self._title_lbl.setText(
            fm.elidedText(title, Qt.ElideRight, 260))
        self._artist_lbl.setText(artist)
        self._duration_ms = duration_ms
        self._current_ms  = 0
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
        items:         List[Tuple[str, Dict]],
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
        while self._queue_inner_lay.count() > 1:
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

        if 0 <= self._current_idx < self._queue_inner_lay.count() - 1:
            w = self._queue_inner_lay.itemAt(self._current_idx).widget()
            if w:
                QTimer.singleShot(
                    50, lambda: self._queue_scroll.ensureWidgetVisible(w))


# ── helper ────────────────────────────────────────────────────────

def _fmt_ms(ms: int) -> str:
    secs = int(ms / 1000)
    m, s = divmod(secs, 60)
    return f"{m}:{s:02d}"
