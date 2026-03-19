"""
PlaylistsPage — shows local playlist folders as PlaylistCard widgets.
Supports creating, deleting, and opening playlists.
No placeholder content.
"""
from __future__ import annotations

import os
import shutil
from typing import List

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QFrame, QGridLayout,
    QSizePolicy, QMessageBox
)

from app.desktop.config import config
from app.desktop.utils.metadata import get_audio_metadata
from app.desktop.utils.playlist_manager import PlaylistManager
from app.desktop.ui.widgets.playlist_card import PlaylistCard
from app.desktop.ui.dialogs.create_playlist_dialog import CreatePlaylistDialog


class PlaylistsPage(QWidget):
    """
    Signals
    -------
    playlist_play_requested(folder_path)
    song_play_requested(file_path, metadata)
    """
    playlist_play_requested = pyqtSignal(str)
    song_play_requested     = pyqtSignal(str, dict)

    CARD_W = 210   # px per card column

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: List[PlaylistCard] = []
        self._all_playlists: list = []   # raw PlaylistManager data
        self._build()

    # ── build ──────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 16)
        root.setSpacing(16)

        # ── header row ──
        hdr = QHBoxLayout()

        title = QLabel("Your Playlists")
        title.setStyleSheet(
            "font-size: 26px; font-weight: 800; color: #ffffff; background: transparent;"
        )
        hdr.addWidget(title)
        hdr.addStretch()

        # search filter
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter playlists…")
        self._search.setFixedWidth(180)
        self._search.setFixedHeight(36)
        self._search.textChanged.connect(self._filter)
        hdr.addWidget(self._search)

        # new playlist button
        new_btn = QPushButton("＋  New Playlist")
        new_btn.setFixedHeight(36)
        new_btn.setProperty("style", "primary")
        new_btn.clicked.connect(self._create_playlist)
        hdr.addWidget(new_btn)

        root.addLayout(hdr)

        # ── count label ──
        self._count_lbl = QLabel("")
        self._count_lbl.setObjectName("see_all_link")
        root.addWidget(self._count_lbl)

        # ── recently added section (horizontal strip) ──
        self._recent_hdr = QLabel("Recently Added Songs")
        self._recent_hdr.setObjectName("section_title")
        self._recent_hdr.setVisible(False)
        root.addWidget(self._recent_hdr)

        self._recent_scroll = QScrollArea()
        self._recent_scroll.setWidgetResizable(True)
        self._recent_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._recent_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._recent_scroll.setFixedHeight(260)
        self._recent_scroll.setFrameShape(QFrame.NoFrame)
        self._recent_scroll.setStyleSheet("background: transparent; border: none;")
        self._recent_scroll.setVisible(False)

        self._recent_inner = QWidget()
        self._recent_inner.setStyleSheet("background: transparent;")
        self._recent_lay = QHBoxLayout(self._recent_inner)
        self._recent_lay.setContentsMargins(0, 0, 0, 0)
        self._recent_lay.setSpacing(14)
        self._recent_lay.addStretch()
        self._recent_scroll.setWidget(self._recent_inner)
        root.addWidget(self._recent_scroll)

        # ── playlists grid ──
        pl_lbl = QLabel("All Playlists")
        pl_lbl.setObjectName("section_title")
        root.addWidget(pl_lbl)

        grid_scroll = QScrollArea()
        grid_scroll.setWidgetResizable(True)
        grid_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        grid_scroll.setFrameShape(QFrame.NoFrame)
        grid_scroll.setStyleSheet("background: transparent; border: none;")

        self._grid_widget = QWidget()
        self._grid_widget.setStyleSheet("background: transparent;")
        self._grid = QGridLayout(self._grid_widget)
        self._grid.setSpacing(16)
        self._grid.setContentsMargins(0, 0, 0, 16)
        self._grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        grid_scroll.setWidget(self._grid_widget)
        root.addWidget(grid_scroll, 1)

        # ── empty state ──
        self._empty = QLabel("No playlists yet. Create one to get started.")
        self._empty.setObjectName("empty_state")
        self._empty.setAlignment(Qt.AlignCenter)
        self._empty.setVisible(False)
        root.addWidget(self._empty)

    # ── public ─────────────────────────────────────────────────

    def refresh(self):
        """Reload everything from disk."""
        self._load_recent_songs()
        self._load_playlists()

    # ── private: recent songs strip ────────────────────────────

    def _load_recent_songs(self):
        # clear
        while self._recent_lay.count() > 1:
            item = self._recent_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        download_path = config.get_download_path()
        if not os.path.isdir(download_path):
            self._recent_hdr.setVisible(False)
            self._recent_scroll.setVisible(False)
            return

        songs = []
        for root_dir, _, files in os.walk(download_path):
            for f in files:
                if f.lower().endswith((".mp3", ".m4a", ".mp4")):
                    fp = os.path.join(root_dir, f)
                    songs.append((fp, os.path.getmtime(fp)))

        songs.sort(key=lambda x: x[1], reverse=True)
        songs = songs[:10]

        if not songs:
            self._recent_hdr.setVisible(False)
            self._recent_scroll.setVisible(False)
            return

        self._recent_hdr.setVisible(True)
        self._recent_scroll.setVisible(True)

        from app.desktop.ui.widgets.song_card import SongCard
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
                card = SongCard(entry)
                card.play_btn.clicked.connect(
                    lambda _, p=fp, m=meta: self.song_play_requested.emit(p, dict(m))
                )
                self._recent_lay.insertWidget(i, card)
            except Exception as exc:
                print(f"[PlaylistsPage] recent: {exc}")

    # ── private: playlists grid ─────────────────────────────────

    def _load_playlists(self):
        download_path = config.get_download_path()
        try:
            self._all_playlists = PlaylistManager.get_all_playlists(download_path)
        except Exception:
            self._all_playlists = []

        self._render_playlists(self._all_playlists)

    def _filter(self, text: str):
        q = text.strip().lower()
        filtered = [
            p for p in self._all_playlists
            if not q or q in p["name"].lower()
        ]
        self._render_playlists(filtered)

    def _render_playlists(self, playlists: list):
        # clear grid
        for card in self._cards:
            try:
                card.setParent(None)
                card.deleteLater()
            except Exception:
                pass
        self._cards.clear()

        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not playlists:
            self._count_lbl.setText("0 playlists")
            self._empty.setVisible(True)
            return

        self._empty.setVisible(False)
        self._count_lbl.setText(
            f"{len(playlists)} playlist{'s' if len(playlists) != 1 else ''}"
        )

        # calculate columns from widget width
        avail = self.width() - 56   # margins
        cols = max(1, avail // (self.CARD_W + 16))

        for i, pl in enumerate(playlists):
            folder_path = pl["folder_path"]
            try:
                card = PlaylistCard(folder_path)
                card.play_requested.connect(self.playlist_play_requested)
                card.delete_requested.connect(self._delete_playlist)
                # single-click opens playlist view inside the card area
                card.mousePressEvent = (
                    lambda ev, fp=folder_path:
                        self.playlist_play_requested.emit(fp)
                        if ev.button() == Qt.LeftButton else None
                )
                self._grid.addWidget(card, i // cols, i % cols)
                self._cards.append(card)
            except Exception as exc:
                print(f"[PlaylistsPage] card: {exc}")

        self._grid.setRowStretch(len(playlists) // cols + 1, 1)

    # ── actions ────────────────────────────────────────────────

    def _create_playlist(self):
        dlg = CreatePlaylistDialog(self)
        if dlg.exec_():
            QTimer.singleShot(200, self.refresh)

    def _delete_playlist(self, folder_path: str):
        name = os.path.basename(folder_path)
        reply = QMessageBox.question(
            self,
            "Delete Playlist",
            f"Delete '{name}' and all its contents?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            try:
                shutil.rmtree(folder_path)
                self.refresh()
            except Exception as exc:
                QMessageBox.warning(self, "Error", str(exc))

    # resize: recalculate columns
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._all_playlists:
            self._render_playlists(
                [p for p in self._all_playlists
                 if not self._search.text().strip()
                 or self._search.text().strip().lower() in p["name"].lower()]
            )