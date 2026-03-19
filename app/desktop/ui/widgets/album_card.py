"""
AlbumCard
─────────
A card widget that displays a YouTube album / playlist.
On click it expands to show the track list; a second click collapses it.
Emits `album_clicked(playlist_id)` so the main window can trigger
a full `playlistItems().list()` fetch.
"""

from __future__ import annotations

from typing import List, Optional

from PyQt5.QtCore import (
    Qt, QSize, QPropertyAnimation, QEasingCurve,
    pyqtSignal, QRect
)
from PyQt5.QtGui import (
    QPainter, QColor, QPixmap, QLinearGradient,
    QBrush, QPen, QFont, QPainterPath
)
from PyQt5.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QWidget, QScrollArea, QSizePolicy
)


# ─────────────────────────────────────────────────────────────────
#  Track row inside the expanded track list
# ─────────────────────────────────────────────────────────────────
class _TrackRow(QWidget):
    play_requested = pyqtSignal(int)   # emits track index

    def __init__(self, index: int, title: str, duration: str = "", parent=None):
        super().__init__(parent)
        self._index = index
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(10)

        num = QLabel(f"{index + 1:02d}")
        num.setObjectName("queue_track_num")
        num.setFixedWidth(24)
        layout.addWidget(num)

        title_lbl = QLabel(title)
        title_lbl.setObjectName("queue_track_title")
        title_lbl.setMaximumWidth(200)
        title_lbl.setWordWrap(False)
        fm_w = title_lbl.fontMetrics().elidedText(title, Qt.ElideRight, 200)
        title_lbl.setText(fm_w)
        layout.addWidget(title_lbl, 1)

        if duration:
            dur = QLabel(duration)
            dur.setObjectName("queue_track_duration")
            layout.addWidget(dur)

        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(32)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.play_requested.emit(self._index)
        super().mousePressEvent(event)

    def enterEvent(self, e):
        self.setStyleSheet("background-color: #141424; border-radius: 6px;")
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.setStyleSheet("")
        super().leaveEvent(e)


# ─────────────────────────────────────────────────────────────────
#  AlbumCard
# ─────────────────────────────────────────────────────────────────
class AlbumCard(QFrame):
    """
    Displays a YouTube playlist identified as an album.

    Signals
    -------
    album_clicked(playlist_id: str)
        Emitted when the card header is clicked (expand/collapse).
    track_play_requested(playlist_id: str, track_index: int)
        Emitted when a specific track row is clicked.
    play_all_requested(playlist_id: str)
        Emitted by the ▶ Play All button.
    """

    album_clicked        = pyqtSignal(str)          # playlist_id
    track_play_requested = pyqtSignal(str, int)      # playlist_id, track_index
    play_all_requested   = pyqtSignal(str)           # playlist_id

    COLLAPSED_HEIGHT = 90
    THUMBNAIL_SIZE   = 70

    def __init__(
        self,
        playlist_id: str,
        title: str,
        artist: str  = "",
        track_count: int = 0,
        album_type: str = "ALBUM",   # "ALBUM", "EP", "PLAYLIST"
        thumbnail_url: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.playlist_id  = playlist_id
        self.album_title  = title
        self.artist       = artist
        self.track_count  = track_count
        self.album_type   = album_type
        self._thumbnail_url = thumbnail_url
        self._expanded    = False
        self._tracks: List[dict] = []   # populated by set_tracks()

        self.setObjectName("album_card_frame")
        self.setFixedHeight(self.COLLAPSED_HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._build_ui()

        # thumbnail loader
        if thumbnail_url:
            self._start_thumb_load()

    # ── build ──────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── header row ──
        self._header = QWidget()
        self._header.setFixedHeight(self.COLLAPSED_HEIGHT)
        self._header.setCursor(Qt.PointingHandCursor)
        self._header.setStyleSheet("background: transparent;")

        hlay = QHBoxLayout(self._header)
        hlay.setContentsMargins(14, 10, 14, 10)
        hlay.setSpacing(12)

        # thumbnail
        self._thumb_label = QLabel()
        self._thumb_label.setFixedSize(self.THUMBNAIL_SIZE, self.THUMBNAIL_SIZE)
        self._thumb_label.setAlignment(Qt.AlignCenter)
        self._set_thumb_placeholder()
        hlay.addWidget(self._thumb_label)

        # meta
        meta = QWidget()
        meta.setStyleSheet("background: transparent;")
        mlay = QVBoxLayout(meta)
        mlay.setContentsMargins(0, 0, 0, 0)
        mlay.setSpacing(3)

        # type badge
        badge = QLabel(self.album_type)
        badge.setObjectName("album_type_badge")
        badge.setFixedHeight(18)
        badge.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        mlay.addWidget(badge)

        # title
        t = QLabel(self.album_title)
        t.setObjectName("album_card_title")
        t.setWordWrap(False)
        fm_w = t.fontMetrics().elidedText(self.album_title, Qt.ElideRight, 220)
        t.setText(fm_w)
        mlay.addWidget(t)

        # artist
        a = QLabel(self.artist)
        a.setObjectName("album_card_artist")
        mlay.addWidget(a)

        # track count
        self._track_count_lbl = QLabel(
            f"{self.track_count} tracks" if self.track_count else "•••"
        )
        self._track_count_lbl.setObjectName("album_track_count")
        mlay.addWidget(self._track_count_lbl)

        mlay.addStretch()
        hlay.addWidget(meta, 1)

        # play all button
        self._play_all_btn = QPushButton("▶")
        self._play_all_btn.setObjectName("card_play_btn")
        self._play_all_btn.setToolTip("Play all tracks")
        self._play_all_btn.setVisible(False)
        self._play_all_btn.clicked.connect(
            lambda: self.play_all_requested.emit(self.playlist_id)
        )
        hlay.addWidget(self._play_all_btn)

        # expand chevron
        self._chevron = QLabel("›")
        self._chevron.setStyleSheet(
            "color: #4a4a65; font-size: 20px; font-weight: 700; background: transparent;"
        )
        hlay.addWidget(self._chevron)

        outer.addWidget(self._header)

        # ── track list (hidden initially) ──
        self._track_container = QWidget()
        self._track_container.setStyleSheet("background: transparent;")
        self._track_layout = QVBoxLayout(self._track_container)
        self._track_layout.setContentsMargins(14, 4, 14, 10)
        self._track_layout.setSpacing(2)
        self._track_container.setVisible(False)
        outer.addWidget(self._track_container)

        # connect header click
        self._header.mousePressEvent = self._on_header_click

    # ── hover ──────────────────────────────────────────────────

    def enterEvent(self, e):
        self._play_all_btn.setVisible(True)
        self._chevron.setStyleSheet(
            "color: #4d59fb; font-size: 20px; font-weight: 700; background: transparent;"
        )
        self.setStyleSheet("""
            QFrame#album_card_frame {
                background-color: #181828;
                border: 1px solid #4d59fb;
                border-radius: 15px;
            }
        """)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._play_all_btn.setVisible(False)
        self._chevron.setStyleSheet(
            "color: #4a4a65; font-size: 20px; font-weight: 700; background: transparent;"
        )
        self.setStyleSheet("""
            QFrame#album_card_frame {
                background-color: #111118;
                border: 1px solid transparent;
                border-radius: 15px;
            }
        """)
        super().leaveEvent(e)

    # ── click – expand / collapse ──────────────────────────────

    def _on_header_click(self, event):
        if event.button() != Qt.LeftButton:
            return
        self._expanded = not self._expanded
        self.album_clicked.emit(self.playlist_id)
        self._animate_expand()

    def _animate_expand(self):
        target_h = (
            self.COLLAPSED_HEIGHT + max(len(self._tracks), 1) * 34 + 16
            if self._expanded
            else self.COLLAPSED_HEIGHT
        )
        self._track_container.setVisible(self._expanded)
        self._chevron.setText("˅" if self._expanded else "›")

        anim = QPropertyAnimation(self, b"minimumHeight", self)
        anim.setDuration(220)
        anim.setStartValue(self.height())
        anim.setEndValue(target_h)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()
        self._expand_anim = anim   # keep ref

        anim2 = QPropertyAnimation(self, b"maximumHeight", self)
        anim2.setDuration(220)
        anim2.setStartValue(self.height())
        anim2.setEndValue(target_h)
        anim2.setEasingCurve(QEasingCurve.OutCubic)
        anim2.start()
        self._expand_anim2 = anim2

    # ── public API ─────────────────────────────────────────────

    def set_tracks(self, tracks: List[dict]) -> None:
        """Populate the expandable track list.

        Each dict should have at minimum: ``title`` and optionally ``duration``.
        """
        self._tracks = tracks
        self.track_count = len(tracks)
        self._track_count_lbl.setText(f"{self.track_count} tracks")

        # clear old rows
        while self._track_layout.count():
            item = self._track_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for i, t in enumerate(tracks):
            row = _TrackRow(
                index=i,
                title=t.get("title", f"Track {i + 1}"),
                duration=t.get("duration", ""),
            )
            row.play_requested.connect(
                lambda idx, pid=self.playlist_id:
                    self.track_play_requested.emit(pid, idx)
            )
            self._track_layout.addWidget(row)

    def set_thumbnail(self, pixmap: QPixmap) -> None:
        scaled = pixmap.scaled(
            self.THUMBNAIL_SIZE, self.THUMBNAIL_SIZE,
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation,
        )
        # clip to rounded rect
        result = QPixmap(self.THUMBNAIL_SIZE, self.THUMBNAIL_SIZE)
        result.fill(Qt.transparent)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.THUMBNAIL_SIZE, self.THUMBNAIL_SIZE, 10, 10)
        painter.setClipPath(path)
        x = (scaled.width() - self.THUMBNAIL_SIZE) // 2
        y = (scaled.height() - self.THUMBNAIL_SIZE) // 2
        painter.drawPixmap(-x, -y, scaled)
        painter.end()
        self._thumb_label.setPixmap(result)

    # ── helpers ────────────────────────────────────────────────

    def _set_thumb_placeholder(self):
        size = self.THUMBNAIL_SIZE
        px = QPixmap(size, size)
        px.fill(QColor("#1a1a3a"))
        p = QPainter(px)
        p.setRenderHint(QPainter.Antialiasing)
        # gradient overlay
        g = QLinearGradient(0, 0, size, size)
        g.setColorAt(0, QColor("#1a1a3a"))
        g.setColorAt(1, QColor("#0d0d20"))
        p.fillRect(0, 0, size, size, g)
        p.setPen(QPen(QColor("#4d59fb")))
        p.setFont(QFont("DM Sans", 24, QFont.Bold))
        p.drawText(0, 0, size, size, Qt.AlignCenter, "💿")
        p.end()
        self._thumb_label.setPixmap(px)

    def _start_thumb_load(self):
        try:
            from app.desktop.threads.thumbnail_loader import ThumbnailLoader
            self._loader = ThumbnailLoader(self._thumbnail_url)
            self._loader.loaded.connect(self.set_thumbnail)
            self._loader.finished.connect(self._on_loader_done)
            self._loader.start()
        except Exception:
            pass

    def _on_loader_done(self):
        try:
            if hasattr(self, "_loader"):
                self._loader.loaded.disconnect()
                self._loader.finished.disconnect()
                self._loader = None
        except Exception:
            pass