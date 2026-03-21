"""
AlbumCard
─────────
A compact card widget that displays a YouTube album / playlist.
Clicking it emits `album_clicked(playlist_id)` to show tracks in the right panel.
No expansion, no play button — clean and compact.
"""

from __future__ import annotations

from typing import List, Optional

from PyQt5.QtCore import (
    Qt, QSize,
    pyqtSignal,
)
from PyQt5.QtGui import (
    QPainter, QColor, QPixmap, QLinearGradient,
    QBrush, QPen, QFont, QPainterPath
)
from PyQt5.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QWidget, QSizePolicy
)


class AlbumCard(QFrame):
    """
    Displays a YouTube playlist identified as an album.
    Clicking it emits album_clicked so the right panel shows tracks.
    """

    album_clicked        = pyqtSignal(str)
    track_play_requested = pyqtSignal(str, int)
    play_all_requested   = pyqtSignal(str)

    COLLAPSED_HEIGHT = 90
    THUMBNAIL_SIZE   = 70

    def __init__(
        self,
        playlist_id: str,
        title: str,
        artist: str  = "",
        track_count: int = 0,
        album_type: str = "ALBUM",
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
        self._tracks: List[dict] = []

        self.setObjectName("album_card_frame")
        self.setFixedHeight(self.COLLAPSED_HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._build_ui()

        if thumbnail_url:
            self._start_thumb_load()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._header = QWidget()
        self._header.setFixedHeight(self.COLLAPSED_HEIGHT)
        self._header.setCursor(Qt.PointingHandCursor)
        self._header.setStyleSheet("background: transparent;")

        hlay = QHBoxLayout(self._header)
        hlay.setContentsMargins(14, 10, 14, 10)
        hlay.setSpacing(12)

        self._thumb_label = QLabel()
        self._thumb_label.setFixedSize(self.THUMBNAIL_SIZE, self.THUMBNAIL_SIZE)
        self._thumb_label.setAlignment(Qt.AlignCenter)
        self._set_thumb_placeholder()
        hlay.addWidget(self._thumb_label)

        meta = QWidget()
        meta.setStyleSheet("background: transparent;")
        mlay = QVBoxLayout(meta)
        mlay.setContentsMargins(0, 0, 0, 0)
        mlay.setSpacing(3)

        badge = QLabel(self.album_type)
        badge.setObjectName("album_type_badge")
        badge.setFixedHeight(18)
        badge.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        mlay.addWidget(badge)

        t = QLabel(self.album_title)
        t.setObjectName("album_card_title")
        t.setWordWrap(False)
        fm_w = t.fontMetrics().elidedText(self.album_title, Qt.ElideRight, 220)
        t.setText(fm_w)
        mlay.addWidget(t)

        a = QLabel(self.artist)
        a.setObjectName("album_card_artist")
        mlay.addWidget(a)

        self._track_count_lbl = QLabel(
            f"{self.track_count} tracks" if self.track_count else "•••"
        )
        self._track_count_lbl.setObjectName("album_track_count")
        mlay.addWidget(self._track_count_lbl)

        mlay.addStretch()
        hlay.addWidget(meta, 1)

        outer.addWidget(self._header)

        self._header.mousePressEvent = self._on_header_click

    def enterEvent(self, e):
        self.setStyleSheet("""
            QFrame#album_card_frame {
                background-color: #181828;
                border: 1px solid #4d59fb;
                border-radius: 15px;
            }
        """)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.setStyleSheet("""
            QFrame#album_card_frame {
                background-color: #111118;
                border: 1px solid transparent;
                border-radius: 15px;
            }
        """)
        super().leaveEvent(e)

    def _on_header_click(self, event):
        if event.button() != Qt.LeftButton:
            return
        self.album_clicked.emit(self.playlist_id)

    def set_tracks(self, tracks: List[dict]) -> None:
        self._tracks = tracks
        self.track_count = len(tracks)
        self._track_count_lbl.setText(f"{self.track_count} tracks")

    def set_thumbnail(self, pixmap: QPixmap) -> None:
        scaled = pixmap.scaled(
            self.THUMBNAIL_SIZE, self.THUMBNAIL_SIZE,
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation,
        )
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

    def _set_thumb_placeholder(self):
        size = self.THUMBNAIL_SIZE
        px = QPixmap(size, size)
        px.fill(QColor("#1a1a3a"))
        p = QPainter(px)
        p.setRenderHint(QPainter.Antialiasing)
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
