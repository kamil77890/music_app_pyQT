"""
PlaylistsPage — app/desktop/ui/pages/playlists_page.py

Two views (QStackedWidget):
  Page 0 — playlist grid + All Songs
  Page 1 — playlist detail: all songs inside one playlist, sorted by artist
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
    QStackedWidget, QFileDialog, QMenu,
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
    All Songs section: only tracks listed in a playlist's playlist.json.
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
#  Background index — all songs from all playlists
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
#  Background thread — songs for one specific playlist, sorted by artist
# ─────────────────────────────────────────────────────────────────
class _PlaylistDetailThread(QThread):
    songs_ready = pyqtSignal(list)   # list of (file_path, metadata_dict)

    def __init__(self, folder_path: str, parent=None):
        super().__init__(parent)
        self._folder = folder_path
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        if self._stop:
            return
        try:
            from app.desktop.utils.metadata import get_audio_metadata

            data = PlaylistManager.get_playlist_info(self._folder)
            entries = []
            for song in data.get("songs", []):
                if self._stop:
                    return
                fp = song.get("file_path", "")
                if not fp or not os.path.isfile(fp):
                    continue
                try:
                    meta = get_audio_metadata(fp, include_cover_data=True)
                    if not isinstance(meta, dict):
                        meta = {}
                    vid = song.get("video_id") or song.get("youtube_id") or ""
                    entry = {
                        "title":        meta.get("title") or
                                        os.path.splitext(os.path.basename(fp))[0],
                        "artist":       meta.get("artist", ""),
                        "duration":     meta.get("duration", 0),
                        "cover_base64": meta.get("cover_base64", ""),
                        "file_path":    fp,
                        "video_id":     vid,
                    }
                    entries.append((fp, entry))
                except Exception as exc:
                    log.warning("Detail meta error %s: %s", os.path.basename(fp), exc)

            # Sort by artist (case-insensitive), Unknown Artist last
            def _artist_key(item):
                a = (item[1].get("artist") or "").strip()
                return ("zzz" if not a or a.lower() == "unknown artist" else a.lower(),
                        (item[1].get("title") or "").lower())

            entries.sort(key=_artist_key)

            if not self._stop:
                self.songs_ready.emit(entries)
        except Exception as exc:
            log.error("PlaylistDetailThread error: %s", exc)
            if not self._stop:
                self.songs_ready.emit([])


# ─────────────────────────────────────────────────────────────────
#  Responsive song grid (same layout as Discover)
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
    playlist_random_requested = pyqtSignal(str)
    song_play_requested     = pyqtSignal(str, dict)
    library_refreshed       = pyqtSignal()

    CARD_W   = 210
    CARD_H   = 240
    CARD_GAP = 16

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards:            List[PlaylistCard] = []
        self._all_playlists:    list               = []
        self._song_cards:         list = []
        self._detail_song_cards:  list = []
        self._all_song_entries:   list = []
        self._selected_paths:     set  = set()
        self._fp_to_entry:        dict = {}
        self._current_detail_folder: str = ""

        self._scan_thread:   Optional[_PlaylistSongsIndexThread] = None
        self._detail_thread: Optional[_PlaylistDetailThread]     = None
        self._rendering: bool = False
        self._pending_sidebar_refresh: bool = False

        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(50)
        self._resize_timer.timeout.connect(self._do_resize_reflow)

        self._build()

    # ── build ──────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top-level stack: page 0 = overview, page 1 = playlist detail
        self._view_stack = QStackedWidget()
        self._view_stack.addWidget(self._build_overview_page())
        self._view_stack.addWidget(self._build_detail_page())
        self._view_stack.setCurrentIndex(0)
        root.addWidget(self._view_stack, 1)

    # ─── Overview page (page 0) ────────────────────────────────

    def _build_overview_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background:transparent;")
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

        # Header
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

        # Playlist grid
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

        # All Songs section
        songs_hdr_row = QHBoxLayout()
        songs_sec = QLabel("All Songs (in playlists)")
        songs_sec.setObjectName("section_title")
        songs_hdr_row.addWidget(songs_sec)
        self._sync_lib_btn = QPushButton("⟳  Sync library")
        self._sync_lib_btn.setToolTip(
            "Scan disk and add any new tracks to «All Songs» playlist")
        self._sync_lib_btn.setFixedHeight(32)
        self._sync_lib_btn.setStyleSheet(
            "QPushButton{background:#1e1e38;border:1px solid #2a2a48;"
            "border-radius:8px;color:#c8c8e0;font-weight:600;padding:0 12px;}"
            "QPushButton:hover{background:#2a2a48;color:#fff;}")
        self._sync_lib_btn.clicked.connect(self._on_user_sync_library_clicked)
        songs_hdr_row.addWidget(self._sync_lib_btn)
        songs_hdr_row.addStretch()
        self._songs_count_lbl = QLabel("")
        self._songs_count_lbl.setObjectName("see_all_link")
        songs_hdr_row.addWidget(self._songs_count_lbl)
        self._sel_hint = QLabel("Ctrl+click to select")
        self._sel_hint.setStyleSheet(
            "color:#4a4a65;font-size:11px;background:transparent;")
        songs_hdr_row.addWidget(self._sel_hint)
        self._dl_sel_overview = QPushButton("Download selected")
        self._dl_sel_overview.setProperty("style", "primary")
        self._dl_sel_overview.setFixedHeight(32)
        self._dl_sel_overview.setVisible(False)
        self._dl_sel_overview.clicked.connect(self._download_selected_songs)
        songs_hdr_row.addWidget(self._dl_sel_overview)
        blay.addLayout(songs_hdr_row)

        self._songs_loading_lbl = QLabel("Loading songs…")
        self._songs_loading_lbl.setObjectName("empty_state")
        self._songs_loading_lbl.setAlignment(Qt.AlignCenter)
        self._songs_loading_lbl.setVisible(False)
        blay.addWidget(self._songs_loading_lbl)

        self._empty_songs = QLabel(
            'No songs in your playlists yet \u2014 add tracks to a playlist, or download with \u201cCreate playlist\u201d.')
        self._empty_songs.setObjectName("empty_state")
        self._empty_songs.setAlignment(Qt.AlignCenter)
        self._empty_songs.setVisible(False)
        blay.addWidget(self._empty_songs)

        self._song_grid = _PlaylistSongGrid()
        blay.addWidget(self._song_grid)

        blay.addStretch()
        outer_scroll.setWidget(body)

        ov_lay = QVBoxLayout(page)
        ov_lay.setContentsMargins(0, 0, 0, 0)
        ov_lay.addWidget(outer_scroll)
        return page

    # ─── Detail page (page 1) ──────────────────────────────────

    def _build_detail_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background:transparent;")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ── Sticky header bar ─────────────────────────────────
        hdr_bar = QFrame()
        hdr_bar.setFixedHeight(64)
        hdr_bar.setStyleSheet(
            "background:#0b0b0b;border-bottom:1px solid #141424;")
        hdr_lay = QHBoxLayout(hdr_bar)
        hdr_lay.setContentsMargins(20, 0, 24, 0)
        hdr_lay.setSpacing(12)

        back_btn = QPushButton("← Back")
        back_btn.setStyleSheet(
            "QPushButton{background:transparent;border:none;color:#4d59fb;"
            "font-size:13px;font-weight:700;padding:0 4px;min-height:0;}"
            "QPushButton:hover{color:#7a86ff;}")
        back_btn.setFixedHeight(32)
        back_btn.clicked.connect(self._back_to_playlists)
        hdr_lay.addWidget(back_btn)

        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color:#222235;")
        sep.setFixedWidth(1)
        hdr_lay.addWidget(sep)

        self._detail_title = QLabel("Playlist")
        self._detail_title.setStyleSheet(
            "font-size:18px;font-weight:800;color:#fff;background:transparent;")
        hdr_lay.addWidget(self._detail_title)
        hdr_lay.addStretch()

        self._detail_meta = QLabel("")
        self._detail_meta.setObjectName("see_all_link")
        hdr_lay.addWidget(self._detail_meta)

        self._dl_sel_detail = QPushButton("Download selected")
        self._dl_sel_detail.setProperty("style", "primary")
        self._dl_sel_detail.setFixedHeight(30)
        self._dl_sel_detail.setVisible(False)
        self._dl_sel_detail.clicked.connect(self._download_selected_songs)
        hdr_lay.addWidget(self._dl_sel_detail)

        sort_lbl = QLabel("Sorted by artist A→Z")
        sort_lbl.setStyleSheet(
            "color:#4a4a65;font-size:11px;font-weight:500;background:transparent;")
        hdr_lay.addWidget(sort_lbl)

        lay.addWidget(hdr_bar)

        # ── Scrollable song grid ───────────────────────────────
        self._detail_scroll = QScrollArea()
        self._detail_scroll.setWidgetResizable(True)
        self._detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._detail_scroll.setFrameShape(QFrame.NoFrame)
        self._detail_scroll.setStyleSheet("background:transparent;border:none;")

        detail_body = QWidget()
        detail_body.setStyleSheet("background:transparent;")
        self._detail_lay = QVBoxLayout(detail_body)
        self._detail_lay.setContentsMargins(28, 20, 28, 24)
        self._detail_lay.setSpacing(12)

        self._detail_loading = QLabel("Loading…")
        self._detail_loading.setObjectName("empty_state")
        self._detail_loading.setAlignment(Qt.AlignCenter)
        self._detail_lay.addWidget(self._detail_loading)

        self._detail_empty = QLabel("This playlist has no songs yet.")
        self._detail_empty.setObjectName("empty_state")
        self._detail_empty.setAlignment(Qt.AlignCenter)
        self._detail_empty.setVisible(False)
        self._detail_lay.addWidget(self._detail_empty)

        self._detail_grid = _PlaylistSongGrid()
        self._detail_lay.addWidget(self._detail_grid)
        self._detail_lay.addStretch()

        self._detail_scroll.setWidget(detail_body)
        lay.addWidget(self._detail_scroll, 1)

        return page

    # ── public API ─────────────────────────────────────────────

    def shutdown_background_threads(self) -> None:
        """Zatrzymaj wątki skanowania przy zamykaniu okna (unikaj „QThread destroyed”)."""
        for t in (getattr(self, "_scan_thread", None), getattr(self, "_detail_thread", None)):
            if t is None:
                continue
            try:
                t.stop()
            except Exception:
                pass
            if t.isRunning():
                try:
                    t.wait(4000)
                except Exception:
                    pass

    def refresh(self):
        """Reload overview."""
        self._back_to_playlists()
        self._load_playlists()
        self._load_all_songs()

    def _on_download_library_updated(self, _added: int) -> None:
        """Po każdym pobranym utworze — odśwież siatkę bez ponownego pełnego sync."""
        self._load_all_songs(skip_disk_sync=True)
        self.library_refreshed.emit()

    def _on_user_sync_library_clicked(self) -> None:
        self._pending_sidebar_refresh = True
        self._load_all_songs(skip_disk_sync=False)

    def open_playlist(self, folder_path: str):
        """Switch to detail view for a specific playlist folder."""
        self._show_playlist_detail(folder_path)

    # ── overview ───────────────────────────────────────────────

    def _load_playlists(self):
        try:
            base = config.get_download_path()
            PlaylistManager.ensure_default_playlist(base)
            raw = PlaylistManager.get_all_playlists(base)
            self._all_playlists = PlaylistManager.sort_playlists_default_first(raw, base)
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
                card.random_play_requested.connect(self.playlist_random_requested)
                card.delete_requested.connect(self._delete_playlist)
                # open detail view on click
                card.open_requested.connect(self._show_playlist_detail)

                row = i // cols
                col = i % cols
                x   = col * (self.CARD_W + self.CARD_GAP)
                y   = row * (self.CARD_H + self.CARD_GAP)
                card.setGeometry(x, y, self.CARD_W, self.CARD_H)
                card.show()
                self._cards.append(card)
            except Exception as exc:
                log.warning("Playlist card creation error: %s", exc)

    # resize reflow (debounced)

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

    def _load_all_songs(self, *, skip_disk_sync: bool = False):
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
            if self._pending_sidebar_refresh:
                self._pending_sidebar_refresh = False
                self.library_refreshed.emit()
            return
        try:
            PlaylistManager.ensure_default_playlist(download_path)
        except Exception as exc:
            log.warning("ensure_default_playlist: %s", exc)

        if not skip_disk_sync:
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
        if self._pending_sidebar_refresh:
            self._pending_sidebar_refresh = False
            self.library_refreshed.emit()
        if not songs:
            self._empty_songs.setText(
                'No songs in your playlists yet \u2014 add tracks to a playlist, or download with \u201cCreate playlist\u201d.')
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
                meta = get_audio_metadata(fp, include_cover_data=True) if get_audio_metadata else {}
                if not isinstance(meta, dict):
                    meta = {}
                entry = {
                    "title":        meta.get("title") or os.path.splitext(os.path.basename(fp))[0],
                    "artist":       meta.get("artist", ""),
                    "duration":     meta.get("duration", 0),
                    "cover_base64": meta.get("cover_base64", ""),
                    "file_path":    fp,
                }
                for vk in ("video_id", "youtube_id"):
                    if meta.get(vk):
                        entry[vk] = meta[vk]
                entries.append((fp, entry))
            except Exception as exc:
                log.warning("Metadata read error for %s: %s", os.path.basename(fp), exc)

        self._all_song_entries = entries
        self._render_song_cards(entries)

    def _render_song_cards(self, entries: list):
        self._song_grid.clear()
        self._song_cards.clear()
        self._fp_to_entry = {fp: dict(e) for fp, e in entries}
        self._selected_paths = {
            fp for fp in self._selected_paths if fp in self._fp_to_entry}

        if not entries:
            self._empty_songs.setVisible(True)
            self._update_download_bar()
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
                self._wire_song_card_click(card, fp, entry)
                self._attach_overview_song_menu(card, fp)
                if fp in self._selected_paths:
                    card.set_selected(True)
                cards.append(card)
                self._song_cards.append(card)
            except Exception as exc:
                log.warning("Song card creation error: %s", exc)
        self._song_grid.set_cards(cards)
        self._update_download_bar()

    def _try_cloud_catalog_fallback(self):
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
                    "Check server terminal for B2 traceback and .env.")
            else:
                self._empty_songs.setText(
                    "No local songs — cloud catalog is empty.")
            return

        self._empty_songs.setText("No songs in playlists locally — showing cloud library.")
        self._songs_count_lbl.setText(f"{len(items)} song(s) from cloud")

        entries = []
        for it in items:
            url  = it.get("url") or ""
            key  = it.get("key") or ""
            name = os.path.basename(key) or "track"
            title, artist = _parse_cloud_basename(name)
            entries.append((url, {
                "title": title, "artist": artist, "duration": 0,
                "cover_base64": "", "file_path": url, "stream_url": url,
                "source": "cloud",
            }))

        self._all_song_entries = entries
        self._render_song_cards(entries)

    # ── playlist detail view ────────────────────────────────────

    def _show_playlist_detail(self, folder_path: str):
        """Switch to detail page and load songs sorted by artist."""
        self._clear_song_selection()
        self._current_detail_folder = folder_path
        name = os.path.basename(folder_path)
        self._detail_title.setText(name)
        self._detail_meta.setText("")
        self._detail_loading.setVisible(True)
        self._detail_empty.setVisible(False)
        self._detail_grid.clear()
        self._view_stack.setCurrentIndex(1)
        self._detail_scroll.verticalScrollBar().setValue(0)

        # stop any running detail thread
        if self._detail_thread and self._detail_thread.isRunning():
            self._detail_thread.stop()
            self._detail_thread.wait(500)

        self._detail_thread = _PlaylistDetailThread(folder_path, parent=self)
        self._detail_thread.songs_ready.connect(
            lambda songs, fp=folder_path: self._on_detail_songs_ready(songs, fp))
        self._detail_thread.start()

    def _on_detail_songs_ready(self, songs: list, folder_path: str):
        self._detail_loading.setVisible(False)
        n = len(songs)
        self._detail_meta.setText(
            f"{n} song{'s' if n != 1 else ''}")

        if not songs:
            self._detail_empty.setVisible(True)
            return

        self._detail_empty.setVisible(False)
        self._render_detail_cards(songs)

    def _render_detail_cards(self, entries: list):
        self._detail_grid.clear()
        self._detail_song_cards.clear()
        folder = getattr(self, "_current_detail_folder", "") or ""
        for fp, e in entries:
            merged = dict(e)
            if folder:
                merged["from_playlist_folder"] = folder
            self._fp_to_entry[fp] = merged
        self._selected_paths = {
            fp for fp in self._selected_paths if fp in self._fp_to_entry}

        from app.desktop.ui.widgets.song_card import SongCard
        cards = []
        for fp, entry in entries:
            try:
                e = dict(entry)
                if folder:
                    e["from_playlist_folder"] = folder
                card = SongCard(e)
                card._file_path = fp
                card.play_btn.clicked.connect(
                    lambda _, f=fp, ex=e: self.song_play_requested.emit(f, ex))
                self._wire_song_card_click(card, fp, e)
                self._attach_detail_song_menu(card, fp)
                if fp in self._selected_paths:
                    card.set_selected(True)
                cards.append(card)
                self._detail_song_cards.append(card)
            except Exception as exc:
                log.warning("Detail card error: %s", exc)
        self._detail_grid.set_cards(cards)
        self._update_download_bar()

    def _attach_overview_song_menu(self, card, fp: str) -> None:
        card.setContextMenuPolicy(Qt.CustomContextMenu)
        card.customContextMenuRequested.connect(
            lambda pos, c=card, f=fp: self._on_overview_song_menu(c, f, pos))

    def _attach_detail_song_menu(self, card, fp: str) -> None:
        card.setContextMenuPolicy(Qt.CustomContextMenu)
        card.customContextMenuRequested.connect(
            lambda pos, c=card, f=fp: self._on_detail_song_menu(c, f, pos))

    def _on_overview_song_menu(self, card, fp: str, pos) -> None:
        menu = QMenu(card)
        sub = menu.addMenu("Add to playlist…")
        base = config.get_download_path()
        try:
            playlists = PlaylistManager.sort_playlists_default_first(
                PlaylistManager.get_all_playlists(base), base)
        except Exception:
            playlists = []
        for pl in playlists:
            name = (pl.get("name") or pl.get("folder_name") or "").strip() or "Playlist"
            pdir = pl.get("folder_path") or ""
            if not pdir:
                continue
            sub.addAction(name).triggered.connect(
                lambda checked=False, folder=pdir, path=fp: self._add_file_to_playlist(
                    folder, path))
        if not sub.actions():
            sub.addAction("(No playlists)").setEnabled(False)
        menu.exec_(card.mapToGlobal(pos))

    def _on_detail_song_menu(self, card, fp: str, pos) -> None:
        menu = QMenu(card)
        act = menu.addAction("Remove from this playlist")
        act.triggered.connect(
            lambda: self._remove_song_from_current_playlist(fp))
        menu.exec_(card.mapToGlobal(pos))

    def _add_file_to_playlist(self, playlist_folder: str, file_path: str) -> None:
        if not file_path or not os.path.isfile(file_path):
            QMessageBox.warning(self, "Playlist", "File not found.")
            return
        try:
            from app.desktop.utils.metadata import get_audio_metadata
            meta = get_audio_metadata(file_path)
        except Exception:
            meta = {}
        ok = PlaylistManager.add_song_to_playlist(playlist_folder, file_path, meta)
        if ok:
            QMessageBox.information(self, "Playlist", "Song added to the playlist.")
            self._load_all_songs()
        else:
            QMessageBox.information(
                self, "Playlist",
                "Could not add (already in that playlist or error).")

    def _remove_song_from_current_playlist(self, fp: str) -> None:
        folder = self._current_detail_folder
        if not folder:
            return
        if PlaylistManager.remove_song_by_file_path(folder, fp):
            self._show_playlist_detail(folder)
        else:
            QMessageBox.warning(self, "Playlist", "Could not remove song.")

    def _all_selectable_cards(self):
        return [c for c in self._song_cards + self._detail_song_cards if c]

    def _clear_song_selection(self):
        for c in self._all_selectable_cards():
            try:
                c.set_selected(False)
            except Exception:
                pass
        self._selected_paths.clear()
        self._update_download_bar()

    def _update_download_bar(self):
        n = len(self._selected_paths)
        for btn in (getattr(self, "_dl_sel_overview", None),
                    getattr(self, "_dl_sel_detail", None)):
            if btn is not None:
                btn.setVisible(n > 0)
                btn.setText(
                    f"Download selected ({n})" if n else "Download selected")

    def _wire_song_card_click(self, card, fp: str, entry: dict):
        def _on_press(ev):
            if ev.button() != Qt.LeftButton:
                return
            if ev.modifiers() & Qt.ControlModifier:
                if fp in self._selected_paths:
                    self._selected_paths.discard(fp)
                    card.set_selected(False)
                else:
                    self._selected_paths.add(fp)
                    card.set_selected(True)
                self._update_download_bar()
                return
            for c in self._all_selectable_cards():
                c.set_selected(False)
            self._selected_paths.clear()
            self.song_play_requested.emit(fp, entry)
            self._update_download_bar()
        card.mousePressEvent = _on_press

    def _download_selected_songs(self):
        if not self._selected_paths:
            return
        from app.desktop.utils.helpers import clean_video_id
        from app.desktop.ui.dialogs.download_manager_dialog import DownloadManagerDialog

        yt_rows = []
        local_only = []
        for fp in self._selected_paths:
            entry = dict(self._fp_to_entry.get(fp) or {})
            is_url = isinstance(fp, str) and fp.startswith(
                ("http://", "https://"))
            vid = None
            for k in ("video_id", "id", "youtube_id"):
                v = entry.get(k)
                if v and str(v).strip():
                    vid = clean_video_id(str(v).strip())
                    if vid:
                        break
            if not vid:
                try:
                    from app.desktop.utils.metadata import get_audio_metadata
                    m = get_audio_metadata(fp)
                    for k in ("video_id", "youtube_id"):
                        if m.get(k):
                            vid = clean_video_id(str(m.get(k)))
                            if vid:
                                break
                except Exception:
                    pass
            if vid:
                yt_rows.append({
                    "title": entry.get("title", os.path.basename(fp)),
                    "artist": entry.get("artist", "Unknown Artist"),
                    "video_id": vid,
                    "file_path": fp,
                })
            elif is_url:
                continue
            else:
                local_only.append(fp)

        if yt_rows:
            dlg = DownloadManagerDialog(
                songs=yt_rows,
                download_path=config.get_download_path(),
                parent=self,
            )
            dlg.download_finished.connect(lambda _: None)
            dlg.library_updated.connect(self._on_download_library_updated)
            dlg.show()

        if local_only:
            dest = QFileDialog.getExistingDirectory(
                self, "Copy selected files to folder…")
            if dest:
                nok = 0
                for fp in local_only:
                    try:
                        shutil.copy2(
                            fp, os.path.join(dest, os.path.basename(fp)))
                        nok += 1
                    except Exception as exc:
                        log.warning("Copy failed: %s", exc)
                QMessageBox.information(
                    self, "Done", f"Copied {nok} file(s) to the chosen folder.")

        if not yt_rows and not local_only and self._selected_paths:
            QMessageBox.information(
                self, "Nothing to download",
                "No YouTube video ID on the selected items, or only cloud "
                "streams selected.")

    def _back_to_playlists(self):
        """Return to the overview (page 0)."""
        self._clear_song_selection()
        self._view_stack.setCurrentIndex(0)
        if self._detail_thread and self._detail_thread.isRunning():
            self._detail_thread.stop()

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
                self, "Cannot delete",
                "The «All Songs» playlist is your default library and cannot be deleted.")
            return
        name = os.path.basename(folder_path)
        reply = QMessageBox.question(
            self, "Delete Playlist",
            f"Delete '{name}' and all its contents?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            try:
                shutil.rmtree(folder_path)
                self.refresh()
            except Exception as exc:
                QMessageBox.warning(self, "Error", str(exc))
