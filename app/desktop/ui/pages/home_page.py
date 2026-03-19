"""
HomePage — shows recently downloaded songs from the local library.
No placeholder content: shows empty state if the library is empty.
"""
from __future__ import annotations

import os
from typing import List

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QFrame, QGridLayout, QSizePolicy
)

from app.desktop.config import config
from app.desktop.utils.metadata import get_audio_metadata


class HomePage(QWidget):
    """
    Signals
    -------
    song_play_requested(file_path, metadata)
    """
    song_play_requested = pyqtSignal(str, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._song_cards: list = []
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(20)

        # ── header ──
        hdr = QHBoxLayout()
        title = QLabel("Good listening 👋")
        title.setObjectName("section_title")
        title.setStyleSheet(
            "font-size: 26px; font-weight: 800; color: #ffffff; background: transparent;"
        )
        hdr.addWidget(title)
        hdr.addStretch()

        self._count_lbl = QLabel("")
        self._count_lbl.setObjectName("see_all_link")
        hdr.addWidget(self._count_lbl)
        root.addLayout(hdr)

        # ── recently added label ──
        sec_lbl = QLabel("Recently Added")
        sec_lbl.setObjectName("section_title")
        root.addWidget(sec_lbl)

        # ── scrollable song grid ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")

        self._grid_widget = QWidget()
        self._grid_widget.setStyleSheet("background: transparent;")
        self._grid = QGridLayout(self._grid_widget)
        self._grid.setSpacing(16)
        self._grid.setContentsMargins(0, 0, 0, 16)
        self._grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        scroll.setWidget(self._grid_widget)
        root.addWidget(scroll, 1)

        # ── empty state ──
        self._empty = QLabel(
            "Your library is empty.\nUse Discover to find and download music."
        )
        self._empty.setObjectName("empty_state")
        self._empty.setAlignment(Qt.AlignCenter)
        self._empty.setVisible(False)
        root.addWidget(self._empty)

    # ── public ─────────────────────────────────────────────────

    def refresh(self):
        """Reload from disk (call when switching to this page)."""
        self._clear_grid()
        self._song_cards.clear()

        download_path = config.get_download_path()
        if not os.path.isdir(download_path):
            self._show_empty()
            return

        songs = []
        for root_dir, _, files in os.walk(download_path):
            for f in files:
                if f.lower().endswith((".mp3", ".m4a", ".mp4")):
                    fp = os.path.join(root_dir, f)
                    songs.append((fp, os.path.getmtime(fp)))

        songs.sort(key=lambda x: x[1], reverse=True)
        songs = songs[:40]   # cap for performance

        if not songs:
            self._show_empty()
            return

        self._empty.setVisible(False)
        self._count_lbl.setText(f"{len(songs)} songs")

        cols = 5
        for i, (fp, _) in enumerate(songs):
            try:
                meta = get_audio_metadata(fp)
                entry = {
                    "title":     meta.get("title", os.path.splitext(os.path.basename(fp))[0]),
                    "artist":    meta.get("artist", "Unknown Artist"),
                    "cover":     meta.get("cover_url", ""),
                    "thumbnail": meta.get("thumbnail", ""),
                    "file_path": fp,
                }
                from app.desktop.ui.widgets.song_card import SongCard
                card = SongCard(entry)
                card.play_btn.clicked.connect(
                    lambda _, p=fp, m=meta: self.song_play_requested.emit(p, dict(m))
                )
                card.mouseDoubleClickEvent = (
                    lambda ev, p=fp, m=meta:
                        self.song_play_requested.emit(p, dict(m))
                        if ev.button() == Qt.LeftButton else None
                )
                self._grid.addWidget(card, i // cols, i % cols)
                self._song_cards.append(card)
            except Exception as exc:
                print(f"[HomePage] {exc}")

        self._grid.setRowStretch(len(songs) // cols + 1, 1)

    # ── private ────────────────────────────────────────────────

    def _clear_grid(self):
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _show_empty(self):
        self._count_lbl.setText("")
        self._empty.setVisible(True)