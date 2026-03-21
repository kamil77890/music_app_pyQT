"""
PlaylistsPage — app/desktop/ui/pages/playlists_page.py

Uses the same SongCard layout as the Discover search results.
The filter input searches both playlists AND songs by title/artist.
"""
from __future__ import annotations

import logging
import os
import shutil
from typing import List, Optional

log = logging.getLogger(__name__)

from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QFrame, QSizePolicy, QMessageBox,
)

from app.desktop.config import config
from app.desktop.utils.playlist_manager import PlaylistManager
from app.desktop.ui.widgets.playlist_card import PlaylistCard
from app.desktop.ui.dialogs.create_playlist_dialog import CreatePlaylistDialog


def _real_key(path: str) -> str:
    try:
        return os.path.normcase(os.path.realpath(path))
    except OSError:
        return os.path.normcase(path)


def _paths_from_playlist_jsons(base_path: str) -> list:
    """Collect file_path entries from every playlist.json (songs in your playlists)."""
    out = []
    try:
        for pl in PlaylistManager.get_all_playlists(base_path):
            for s in pl.get("songs", []):
                fp = s.get("file_path")
                if fp and os.path.isfile(fp):
                    out.append(fp)
    except Exception as exc:
        log.warning("Playlist JSON paths error: %s", exc)
    return out


def _all_songs_from_playlists_only(base_path: str) -> list:
    """
    All Songs section: **only** tracks listed in a playlist's playlist.json
    (not loose files elsewhere under the download folder).
    Deduped by real path, newest first.
    """
    seen = set()
    rows = []
    for fp in _paths_from_playlist_jsons(base_path):
        k = _real_key(fp)
        if k in seen:
            continue
        seen.add(k)
        try:
            rows.append((fp, os.path.getmtime(fp)))
        except OSError:
            rows.append((fp, 0))
    rows.sort(key=lambda x: x[1], reverse=True)
    return rows


def _parse_cloud_basename(name: str) -> tuple:
    base = os.path.splitext(name)[0]
    if " - " in base:
        a, t = base.split(" - ", 1)
        return t.strip(), a.strip()
    return base, "Unknown Artist"


# ─────────────────────────────────────────────────────────────────
#  Background index — only songs referenced in playlist.json files
# ─────────────────────────────────────────────────────────────────
class _PlaylistSongsIndexThread(QThread):
    songs_ready = pyqtSignal(list)

    def __init__(self, download_path: str, parent=None):
        super().__init__(parent)
        self._path = download_path
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        if self._stop:
            return
        try:
            songs = _all_songs_from_playlists_only(self._path)
        except Exception as exc:
            log.error("Playlist songs index error: %s", exc)
            songs = []
        if not self._stop:
            self.songs_ready.emit(songs)


# ─────────────────────────────────────────────────────────────────
#  Responsive song grid (same as Discover)
# ─────────────────────────────────────────────────────────────────
class _PlaylistSongGrid(QWidget):
    MIN_CARD_W = 180
    CARD_H     = 280
    SPACING    = 14

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")
        self._cards: list = []

    def set_cards(self, cards: list):
        for c in self._cards:
            try: c.setParent(None)
            except: pass
        self._cards = list(cards)
        for c in self._cards:
            c.setParent(self); c.show()
        self._relayout()

    def clear(self):
        for c in self._cards:
            try: c.deleteLater()
            except: pass
        self._cards.clear()
        self.setMinimumHeight(0); self.setMaximumHeight(16_777_215)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout()

    def _cols(self):
        return max(1, (max(self.width(), 1) + self.SPACING) // (self.MIN_CARD_W + self.SPACING))

    def _card_w(self):
        cols = self._cols()
        return max(self.MIN_CARD_W, (self.width() - (cols - 1) * self.SPACING) // cols)

    def _relayout(self):
        if not self._cards:
            self.setMinimumHeight(0); return
        cols = self._cols(); cw = self._card_w()
        for i, card in enumerate(self._cards):
            row = i // cols; col = i % cols
            card.setFixedSize(cw, self.CARD_H)
            card.move(col * (cw + self.SPACING), row * (self.CARD_H + self.SPACING))
        rows = (len(self._cards) + cols - 1) // cols
        h = rows * self.CARD_H + (rows - 1) * self.SPACING + 10
        self.setMinimumHeight(h); self.setMaximumHeight(h)


# ─────────────────────────────────────────────────────────────────
#  PlaylistsPage
# ─────────────────────────────────────────────────────────────────
class PlaylistsPage(QWidget):
    playlist_play_requested = pyqtSignal(str)
    song_play_requested     = pyqtSignal(str, dict)

    CARD_W   = 210
    CARD_H   = 240
    CARD_GAP = 16

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards:          List[PlaylistCard]       = []
        self._all_playlists:  list                     = []
        self._song_cards:     list                     = []
        self._all_song_entries: list                   = []
        self._scan_thread:    Optional[_PlaylistSongsIndexThread] = None

        self._rendering: bool = False

        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(50)
        self._resize_timer.timeout.connect(self._do_resize_reflow)

        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        outer_scroll = QScrollArea()
        outer_scroll.setWidgetResizable(True)
        outer_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer_scroll.setFrameShape(QFrame.NoFrame)
        outer_scroll.setStyleSheet("background:transparent;border:none;")

        body = QWidget()
        body.setStyleSheet("background:transparent;")
        blay = QVBoxLayout(body)
        blay.setContentsMargins(28, 24, 28, 24)
        blay.setSpacing(16)

        # ── Header ────────────────────────────────────────────
        hdr = QHBoxLayout()
        title_lbl = QLabel("Your Playlists")
        title_lbl.setStyleSheet(
            "font-size:26px;font-weight:800;color:#fff;background:transparent;")
        hdr.addWidget(title_lbl)
        hdr.addStretch()

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search playlists & songs…")
        self._search.setFixedWidth(220)
        self._search.setFixedHeight(36)
        self._search.textChanged.connect(self._filter)
        hdr.addWidget(self._search)

        new_btn = QPushButton("＋  New Playlist")
        new_btn.setFixedHeight(36)
        new_btn.setProperty("style", "primary")
        new_btn.clicked.connect(self._create_playlist)
        hdr.addWidget(new_btn)
        blay.addLayout(hdr)

        self._count_lbl = QLabel("")
        self._count_lbl.setObjectName("see_all_link")
        blay.addWidget(self._count_lbl)

        # ── Playlist grid container ───────────────────────────
        pl_sec = QLabel("All Playlists")
        pl_sec.setObjectName("section_title")
        blay.addWidget(pl_sec)

        self._grid_host = QWidget()
        self._grid_host.setStyleSheet("background:transparent;")
        blay.addWidget(self._grid_host)

        self._empty_pl = QLabel("No playlists yet — create one to get started.")
        self._empty_pl.setObjectName("empty_state")
        self._empty_pl.setAlignment(Qt.AlignCenter)
        self._empty_pl.setVisible(False)
        blay.addWidget(self._empty_pl)

        # ── All Songs section ─────────────────────────────────
        songs_hdr_row = QHBoxLayout()
        songs_sec = QLabel("All Songs (in playlists)")
        songs_sec.setObjectName("section_title")
        songs_hdr_row.addWidget(songs_sec)
        songs_hdr_row.addStretch()
        self._songs_count_lbl = QLabel("")
        self._songs_count_lbl.setObjectName("see_all_link")
        songs_hdr_row.addWidget(self._songs_count_lbl)
        blay.addLayout(songs_hdr_row)

        self._songs_loading_lbl = QLabel("Loading songs…")
        self._songs_loading_lbl.setObjectName("empty_state")
        self._songs_loading_lbl.setAlignment(Qt.AlignCenter)
        self._songs_loading_lbl.setVisible(False)
        blay.addWidget(self._songs_loading_lbl)

        self._empty_songs = QLabel(
            "No songs in your playlists yet — add tracks to a playlist, or download with “Create playlist”.")
        self._empty_songs.setObjectName("empty_state")
        self._empty_songs.setAlignment(Qt.AlignCenter)
        self._empty_songs.setVisible(False)
        blay.addWidget(self._empty_songs)

        self._song_grid = _PlaylistSongGrid()
        blay.addWidget(self._song_grid)

        blay.addStretch()
        outer_scroll.setWidget(body)
        root.addWidget(outer_scroll, 1)

    # ── public ─────────────────────────────────────────────────

    def refresh(self):
        self._load_playlists()
        self._load_all_songs()

    # ── playlists ──────────────────────────────────────────────

    def _load_playlists(self):
        try:
            base = config.get_download_path()
            PlaylistManager.ensure_default_playlist(base)
            raw = PlaylistManager.get_all_playlists(base)
            self._all_playlists = PlaylistManager.sort_playlists_default_first(
                raw, base)
        except Exception:
            self._all_playlists = []
        self._render_playlists(self._all_playlists)

    def _filter(self, text: str):
        q = text.strip().lower()
        filtered = [p for p in self._all_playlists
                    if not q or q in p["name"].lower()]
        self._render_playlists(filtered)

        if q and self._all_song_entries:
            filtered_songs = [
                (fp, entry) for fp, entry in self._all_song_entries
                if q in entry.get("title", "").lower()
                or q in entry.get("artist", "").lower()
            ]
            self._render_song_cards(filtered_songs)
        elif not q and self._all_song_entries:
            self._render_song_cards(
                [(fp, entry) for fp, entry in self._all_song_entries])

    def _render_playlists(self, playlists: list):
        if self._rendering:
            return
        self._rendering = True
        try:
            self._do_render_playlists(playlists)
        finally:
            self._rendering = False

    def _do_render_playlists(self, playlists: list):
        for card in self._cards:
            try:
                card.setParent(None)
                card.deleteLater()
            except Exception:
                pass
        self._cards.clear()

        if not playlists:
            self._count_lbl.setText("0 playlists")
            self._empty_pl.setVisible(True)
            self._grid_host.setFixedHeight(0)
            return

        self._empty_pl.setVisible(False)
        self._count_lbl.setText(
            f"{len(playlists)} playlist{'s' if len(playlists) != 1 else ''}")

        avail = max(self.width() - 56, self.CARD_W + self.CARD_GAP)
        cols  = max(1, (avail + self.CARD_GAP) // (self.CARD_W + self.CARD_GAP))
        rows  = (len(playlists) + cols - 1) // cols

        host_h = rows * self.CARD_H + (rows - 1) * self.CARD_GAP
        self._grid_host.setFixedHeight(host_h)

        for i, pl in enumerate(playlists):
            try:
                card = PlaylistCard(pl["folder_path"])
                card.setParent(self._grid_host)
                card.play_requested.connect(self.playlist_play_requested)
                card.delete_requested.connect(self._delete_playlist)

                row = i // cols
                col = i % cols
                x   = col * (self.CARD_W + self.CARD_GAP)
                y   = row * (self.CARD_H + self.CARD_GAP)
                card.setGeometry(x, y, self.CARD_W, self.CARD_H)
                card.show()
                self._cards.append(card)
            except Exception as exc:
                log.warning("Playlist card creation error: %s", exc)

    # ── resize: reflow card positions (debounced) ──────────────

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_timer.start()

    def _do_resize_reflow(self):
        if not self._cards or self._rendering:
            return

        avail = max(self.width() - 56, self.CARD_W + self.CARD_GAP)
        cols  = max(1, (avail + self.CARD_GAP) // (self.CARD_W + self.CARD_GAP))
        rows  = (len(self._cards) + cols - 1) // cols

        host_h = rows * self.CARD_H + (rows - 1) * self.CARD_GAP
        self._grid_host.setFixedHeight(host_h)

        for i, card in enumerate(self._cards):
            row = i // cols
            col = i % cols
            x   = col * (self.CARD_W + self.CARD_GAP)
            y   = row * (self.CARD_H + self.CARD_GAP)
            card.setGeometry(x, y, self.CARD_W, self.CARD_H)

    # ── all songs ───────────────────────────────────────────────

    def _load_all_songs(self):
        self._song_grid.clear()
        self._song_cards.clear()
        self._all_song_entries.clear()

        self._empty_songs.setVisible(False)
        self._songs_loading_lbl.setVisible(True)
        self._songs_count_lbl.setText("")

        download_path = config.get_download_path()
        if not os.path.isdir(download_path):
            self._songs_loading_lbl.setVisible(False)
            self._empty_songs.setVisible(True)
            return
        try:
            PlaylistManager.ensure_default_playlist(download_path)
        except Exception as exc:
            log.warning("ensure_default_playlist: %s", exc)

        # Backfill playlist.json from disk (e.g. flat MP3s in «All Songs» like music-server layout)
        try:
            from app.desktop.utils.auto_playlist import get_auto_playlist_manager

            mgr = get_auto_playlist_manager(download_path)
            n = mgr.sync_from_library(download_path)
            if n:
                log.info("Synced %d file(s) into All Songs playlist.json", n)
        except Exception as exc:
            log.warning("sync_from_library: %s", exc)

        if self._scan_thread is not None:
            self._scan_thread.stop()
            if self._scan_thread.isRunning():
                self._scan_thread.quit()
                self._scan_thread.wait(1000)
            self._scan_thread = None

        self._scan_thread = _PlaylistSongsIndexThread(download_path, parent=self)
        self._scan_thread.songs_ready.connect(self._on_songs_scanned)
        self._scan_thread.start()

    def _on_songs_scanned(self, songs: list):
        self._songs_loading_lbl.setVisible(False)

        if not songs:
            self._empty_songs.setText(
                "No songs in your playlists yet — add tracks to a playlist, or download with “Create playlist”.")
            self._try_cloud_catalog_fallback()
            return

        self._songs_count_lbl.setText(
            f"{len(songs)} song{'s' if len(songs) != 1 else ''}")

        self._process_songs(songs)

    def _process_songs(self, songs: list):
        try:
            from app.desktop.utils.metadata import get_audio_metadata
        except ImportError:
            get_audio_metadata = None

        entries = []
        for fp, _ in songs:
            try:
                if get_audio_metadata:
                    meta = get_audio_metadata(fp, include_cover_data=True)
                    if not isinstance(meta, dict):
                        meta = {}
                else:
                    meta = {}

                entry = {
                    "title":    meta.get("title") or
                                os.path.splitext(os.path.basename(fp))[0],
                    "artist":   meta.get("artist", ""),
                    "duration": meta.get("duration", 0),
                    "cover_base64": meta.get("cover_base64", ""),
                    "file_path": fp,
                }
                entries.append((fp, entry))
            except Exception as exc:
                log.warning("Metadata read error for %s: %s", os.path.basename(fp), exc)

        self._all_song_entries = entries
        self._render_song_cards(entries)

    def _render_song_cards(self, entries: list):
        self._song_grid.clear()
        self._song_cards.clear()

        if not entries:
            self._empty_songs.setVisible(True)
            return

        self._empty_songs.setVisible(False)

        from app.desktop.ui.widgets.song_card import SongCard

        cards = []
        for fp, entry in entries:
            try:
                card = SongCard(entry)
                card._file_path = fp

                card.play_btn.clicked.connect(
                    lambda _, f=fp, e=entry: self.song_play_requested.emit(f, e))

                def _click(ev, f=fp, e=entry):
                    if ev.button() == Qt.LeftButton:
                        self.song_play_requested.emit(f, e)
                card.mousePressEvent = _click

                cards.append(card)
                self._song_cards.append(card)
            except Exception as exc:
                log.warning("Song card creation error: %s", exc)

        self._song_grid.set_cards(cards)

    def _try_cloud_catalog_fallback(self):
        """When nothing is downloaded locally, list audio from B2 via API server."""
        try:
            from app.desktop.utils.cloud_client import fetch_cloud_catalog_with_error
        except ImportError:
            self._empty_songs.setVisible(True)
            self._songs_count_lbl.setText("")
            return

        items, err = fetch_cloud_catalog_with_error(400)
        if not items:
            self._empty_songs.setVisible(True)
            self._songs_count_lbl.setText("")
            if err:
                self._empty_songs.setText(
                    f"No local songs — cloud catalog failed ({err}). "
                    "Check server terminal for B2 traceback and .env (ENDPOINT_URL, B2_KEY_ID, B2_APPLICATION_KEY, BUCKET_NAME)."
                )
            else:
                self._empty_songs.setText(
                    "No local songs — cloud catalog is empty (nothing uploaded under music/ yet)."
                )
            return

        self._empty_songs.setText(
            "No songs in playlists locally — showing cloud library.")
        self._songs_count_lbl.setText(
            f"{len(items)} song(s) from cloud")

        entries = []
        for it in items:
            url = it.get("url") or ""
            key = it.get("key") or ""
            name = os.path.basename(key) or "track"
            title, artist = _parse_cloud_basename(name)
            entries.append(
                (
                    url,
                    {
                        "title": title,
                        "artist": artist,
                        "duration": 0,
                        "cover_base64": "",
                        "file_path": url,
                        "stream_url": url,
                        "source": "cloud",
                    },
                )
            )

        self._all_song_entries = entries
        self._render_song_cards(entries)

    # ── actions ────────────────────────────────────────────────

    def _create_playlist(self):
        try:
            dlg = CreatePlaylistDialog(self)
            if dlg.exec_():
                QTimer.singleShot(200, self.refresh)
        except Exception as exc:
            log.error("Playlist creation error: %s", exc)

    def _delete_playlist(self, folder_path: str):
        base = config.get_download_path()
        if PlaylistManager.is_default_playlist_folder(folder_path, base):
            QMessageBox.information(
                self,
                "Cannot delete",
                "The «All Songs» playlist is your default library and cannot be deleted.",
            )
            return
        name = os.path.basename(folder_path)
        reply = QMessageBox.question(
            self, "Delete Playlist",
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
