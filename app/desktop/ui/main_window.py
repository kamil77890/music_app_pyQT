"""
main_window.py — Refactored DesktopApp
Three-column layout: Sidebar | QStackedWidget (Home/Discover/Playlists) | PlaybackController

File placement:
  app/desktop/ui/main_window.py                    ← this file
  app/desktop/ui/new_styles.py
  app/desktop/ui/widgets/main_dashboard.py
  app/desktop/ui/widgets/playback_controller.py
  app/desktop/ui/widgets/artist_circle_widget.py
  app/desktop/ui/widgets/album_card.py
  app/desktop/ui/pages/home_page.py
  app/desktop/ui/pages/playlists_page.py
  app/desktop/ui/dialogs/download_manager_dialog.py
  app/desktop/threads/search_thread.py
  app/desktop/threads/download_thread.py           ← updated version
"""

from __future__ import annotations

import os
from typing import Dict, Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSlot
from PyQt5.QtGui import QPainter, QColor, QIcon, QFont, QPixmap
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QSplitter, QStackedWidget,
    QApplication, QSystemTrayIcon, QMenu, QAction, QMessageBox
)

from app.desktop.ui.new_styles                         import get_stylesheet
from app.desktop.ui.widgets.main_dashboard             import MainDashboard
from app.desktop.ui.widgets.playback_controller        import PlaybackController
from app.desktop.ui.pages.home_page                    import HomePage
from app.desktop.ui.pages.playlists_page               import PlaylistsPage
from app.desktop.threads.search_thread                 import SearchThread, AlbumTracksThread
from app.desktop.threads.download_thread               import DownloadThread
from app.desktop.ui.dialogs.download_manager_dialog    import DownloadManagerDialog
from app.desktop.ui.dialogs.fix_metadata_dialog        import FixMetadataDialog

from app.desktop.config                                import config
from app.desktop.ui.widgets.audio_player               import AudioPlayerWidget
from app.desktop.utils.helpers                         import song_to_dict
from app.desktop.utils.playlist_manager               import PlaylistManager


# ─────────────────────────────────────────────────────────────────
#  Page index constants
# ─────────────────────────────────────────────────────────────────
PAGE_HOME      = 0
PAGE_DISCOVER  = 1
PAGE_PLAYLISTS = 2


# ─────────────────────────────────────────────────────────────────
#  Tray icon (programmatic — no file needed)
# ─────────────────────────────────────────────────────────────────
def _make_tray_icon() -> QIcon:
    px = QPixmap(32, 32)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor("#4d59fb"))
    p.setPen(Qt.NoPen)
    p.drawEllipse(0, 0, 32, 32)
    p.setPen(QColor("#ffffff"))
    p.setFont(QFont("Segoe UI", 14, QFont.Bold))
    p.drawText(0, 0, 32, 32, Qt.AlignCenter, "n")
    p.end()
    return QIcon(px)


# ─────────────────────────────────────────────────────────────────
#  Sidebar
# ─────────────────────────────────────────────────────────────────
class _Sidebar(QFrame):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(230)
        self._nav_buttons: Dict[str, QPushButton] = {}
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # logo
        logo_frame = QFrame()
        logo_frame.setFixedHeight(64)
        logo_frame.setStyleSheet("background:transparent;")
        ll = QHBoxLayout(logo_frame)
        ll.setContentsMargins(20, 0, 20, 0)
        logo = QLabel(
            "<span style='color:#4d59fb;font-size:22px;font-weight:900;'>ñ</span>"
            "<span style='color:#e8eaf0;font-size:22px;font-weight:900;'>usic</span>"
        )
        logo.setTextFormat(Qt.RichText)
        logo.setStyleSheet("background:transparent;")
        ll.addWidget(logo)
        root.addWidget(logo_frame)

        # nav — NO Favorites
        nav_frame = QFrame()
        nav_frame.setStyleSheet("background:transparent;")
        nav_lay = QVBoxLayout(nav_frame)
        nav_lay.setContentsMargins(12, 8, 12, 8)
        nav_lay.setSpacing(2)

        for icon, label, key in [
            ("🏠", "Home",      "home"),
            ("🔭", "Discover",  "discover"),
            ("🎵", "Playlists", "playlists"),
        ]:
            btn = QPushButton(f"  {icon}  {label}")
            btn.setObjectName("nav_btn")
            btn.clicked.connect(lambda _, k=key: self._on_nav(k))
            nav_lay.addWidget(btn)
            self._nav_buttons[key] = btn

        root.addWidget(nav_frame)

        # library list
        root.addSpacing(8)
        lbl = QLabel("YOUR LIBRARY")
        lbl.setObjectName("sidebar_section")
        root.addWidget(lbl)
        root.addSpacing(4)

        self._library_frame = QFrame()
        self._library_frame.setStyleSheet("background:transparent;")
        self._library_lay = QVBoxLayout(self._library_frame)
        self._library_lay.setContentsMargins(12, 0, 12, 0)
        self._library_lay.setSpacing(2)
        root.addWidget(self._library_frame)

        root.addStretch()

        # profile
        profile = QFrame()
        profile.setObjectName("sidebar_profile")
        profile.setFixedHeight(60)
        pl = QHBoxLayout(profile)
        pl.setContentsMargins(16, 8, 16, 8)
        pl.setSpacing(10)
        avatar = QLabel("👤")
        avatar.setStyleSheet(
            "font-size:22px;background:#1a1a38;border-radius:16px;padding:4px 6px;")
        avatar.setFixedSize(36, 36)
        pl.addWidget(avatar)
        self._profile_lbl = QLabel("—")
        self._profile_lbl.setObjectName("profile_name")
        pl.addWidget(self._profile_lbl)
        pl.addStretch()
        root.addWidget(profile)

    # ── public ─────────────────────────────────────────────────

    def _on_nav(self, key: str):
        for k, btn in self._nav_buttons.items():
            btn.setProperty("active", "true" if k == key else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def set_active(self, key: str):
        self._on_nav(key)

    def populate_library(self, names: list):
        while self._library_lay.count():
            item = self._library_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for name in names[:8]:
            row = QHBoxLayout()
            dot = QLabel("●")
            dot.setFixedWidth(14)
            dot.setStyleSheet(
                "color:#4d59fb;font-size:8px;background:transparent;")
            row.addWidget(dot)
            lbl = QLabel(name)
            lbl.setObjectName("daily_artist_name")
            row.addWidget(lbl)
            row.addStretch()
            self._library_lay.addLayout(row)


# ─────────────────────────────────────────────────────────────────
#  DesktopApp
# ─────────────────────────────────────────────────────────────────
class DesktopApp(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ñusic — Smart Music Player")

        self._search_thread:   Optional[SearchThread]   = None
        self._album_thread:    Optional[AlbumTracksThread] = None
        self._current_page = "home"

        w, h = config.get("window_size", [1440, 900])
        self.resize(w, h)
        self.setMinimumSize(1100, 720)

        # audio engine
        self._audio = AudioPlayerWidget()
        self._audio.playback_state_changed.connect(self._on_playback_state)
        self._audio.player.positionChanged.connect(self._on_position_changed)

        self.setStyleSheet(get_stylesheet())
        self._build_ui()
        self._setup_tray()
        self._switch_page("home")

        QTimer.singleShot(400,  self._load_sidebar_library)
        QTimer.singleShot(1200, self._check_metadata)

        self.show()
        self._center_window()

    # ── helpers ────────────────────────────────────────────────

    def _center_window(self):
        screen = QApplication.primaryScreen().geometry()
        g = self.geometry()
        self.move(
            (screen.width()  - g.width())  // 2,
            (screen.height() - g.height()) // 2,
        )

    # ── UI ─────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("QSplitter::handle{background:#141424;}")

        # left
        self._sidebar = _Sidebar()
        self._sidebar._nav_buttons["home"].clicked.connect(
            lambda: self._switch_page("home"))
        self._sidebar._nav_buttons["discover"].clicked.connect(
            lambda: self._switch_page("discover"))
        self._sidebar._nav_buttons["playlists"].clicked.connect(
            lambda: self._switch_page("playlists"))
        splitter.addWidget(self._sidebar)

        # centre stack
        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background:#0b0b0b;")

        # Home
        self._home_page = HomePage()
        self._home_page.song_play_requested.connect(self._play_song)
        self._stack.addWidget(self._home_page)           # PAGE_HOME = 0

        # Discover
        self._discover_page = MainDashboard()
        self._discover_page.search_submitted.connect(self._on_search)
        self._discover_page.song_card_double_clicked.connect(self._play_song)
        self._discover_page.song_card_download_clicked.connect(
            self._download_single)
        self._discover_page.download_selected_clicked.connect(
            self._download_songs)
        self._discover_page.download_all_clicked.connect(
            self._download_songs)
        self._discover_page.album_clicked.connect(self._on_album_clicked)
        self._discover_page.artist_clicked.connect(self._on_artist_clicked)
        self._stack.addWidget(self._discover_page)       # PAGE_DISCOVER = 1

        # Playlists
        self._playlists_page = PlaylistsPage()
        self._playlists_page.playlist_play_requested.connect(
            self._play_playlist)
        self._playlists_page.song_play_requested.connect(self._play_song)
        self._stack.addWidget(self._playlists_page)      # PAGE_PLAYLISTS = 2

        splitter.addWidget(self._stack)

        # right — now playing
        self._player = PlaybackController()
        self._player.play_pause_clicked.connect(self._audio.toggle_play)
        self._player.prev_clicked.connect(self._audio.previous_song)
        self._player.next_clicked.connect(self._audio.next_song)
        self._player.seek_requested.connect(
            lambda ms: self._audio.player.setPosition(ms))
        self._player.volume_changed.connect(self._audio.set_volume)
        self._player.shuffle_toggled.connect(self._on_shuffle)
        self._player.repeat_toggled.connect(self._on_repeat)
        self._player.queue_item_double_clicked.connect(self._play_song)
        splitter.addWidget(self._player)

        splitter.setSizes([230, self.width() - 230 - 310, 310])
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(2, False)

        root.addWidget(splitter, 1)

        # audio engine — hidden, backend only
        self._audio.setVisible(False)
        root.addWidget(self._audio)

    # ── page switching ─────────────────────────────────────────

    def _switch_page(self, key: str):
        self._current_page = key
        self._sidebar.set_active(key)
        if key == "home":
            self._stack.setCurrentIndex(PAGE_HOME)
            self._home_page.refresh()
        elif key == "discover":
            self._stack.setCurrentIndex(PAGE_DISCOVER)
        elif key == "playlists":
            self._stack.setCurrentIndex(PAGE_PLAYLISTS)
            self._playlists_page.refresh()

    # ── search ─────────────────────────────────────────────────

    @pyqtSlot(str)
    def _on_search(self, query: str):
        if not query.strip():
            return
        if self._search_thread and self._search_thread.isRunning():
            self._search_thread.stop()
            self._search_thread.quit()

        self._discover_page.show_loading(f'Searching "{query}"…')
        self._stack.setCurrentIndex(PAGE_DISCOVER)
        self._sidebar.set_active("discover")
        self._current_page = "discover"

        self._search_thread = SearchThread(query=query, max_results=20)
        self._search_thread.results_ready.connect(self._on_search_results)
        self._search_thread.error.connect(
            lambda e: self._discover_page.show_loading(f"Search error: {e}"))
        self._search_thread.start()

    @pyqtSlot(list, list, list, str)
    def _on_search_results(self, songs, albums, playlists, _):
        self._discover_page.set_search_results(songs, albums, playlists)

    # ── album expansion ────────────────────────────────────────

    @pyqtSlot(str)
    def _on_album_clicked(self, playlist_id: str):
        if not playlist_id:
            return
        if self._album_thread and self._album_thread.isRunning():
            self._album_thread.stop()
        self._album_thread = AlbumTracksThread(playlist_id=playlist_id)
        self._album_thread.tracks_ready.connect(
            lambda pid, tracks:
                self._discover_page.update_album_card_tracks(pid, tracks))
        self._album_thread.error.connect(
            lambda e: print(f"[AlbumThread] {e}"))
        self._album_thread.start()

    # ── download ───────────────────────────────────────────────

    def _normalise_songs(self, songs: list) -> list:
        """Convert Song models / arbitrary objects → plain dicts."""
        out = []
        for s in songs:
            if isinstance(s, dict):
                out.append(s)
            elif hasattr(s, "model_dump"):
                out.append(s.model_dump())
            elif hasattr(s, "dict"):
                out.append(s.dict())
            else:
                try:
                    out.append(song_to_dict(s))
                except Exception:
                    pass
        return out

    def _download_single(self, entry):
        """Single-song download (▶ button on a card)."""
        songs = self._normalise_songs([entry])
        self._download_songs(songs)

    def _download_songs(self, songs: list):
        """Open DownloadManagerDialog for one or more songs."""
        clean = self._normalise_songs(songs)
        if not clean:
            return
        dlg = DownloadManagerDialog(
            songs         = clean,
            download_path = config.get_download_path(),
            parent        = self,
        )
        dlg.download_finished.connect(self._on_download_done)
        dlg.show()

    @pyqtSlot(str)
    def _on_download_done(self, playlist_name: str):
        QTimer.singleShot(400, self._load_sidebar_library)
        if self._current_page == "playlists":
            QTimer.singleShot(600, self._playlists_page.refresh)

    # ── playback ───────────────────────────────────────────────

    def _play_song(self, file_path: str, metadata: dict):
        try:
            already = any(fp == file_path for fp, _ in self._audio.playlist)
            if not already:
                self._audio.add_to_playlist(file_path, metadata)
            self._audio.play_song(file_path, metadata)

            title  = metadata.get("title",  os.path.basename(file_path))
            artist = metadata.get("artist", "Unknown Artist")
            dur_s  = metadata.get("duration", 0) or 0

            self._player.set_track(title, artist, int(dur_s * 1000))
            self._player.set_playing(True)
            self._player.add_to_queue(file_path, metadata)
        except Exception as exc:
            print(f"[DesktopApp] play error: {exc}")

    # called by DownloadManagerItem
    def play_song_from_manager(self, file_path: str, metadata: dict):
        self._play_song(file_path, metadata)

    def _play_playlist(self, folder_path: str):
        try:
            from app.desktop.utils.helpers import get_mp3_files_recursive
            files = get_mp3_files_recursive(folder_path)
            if not files:
                return
            self._audio.clear_playlist()
            self._player.clear_queue()
            for fp in files:
                try:
                    from app.desktop.utils.metadata import get_audio_metadata
                    meta = get_audio_metadata(fp)
                    self._audio.add_to_playlist(fp, meta)
                    self._player.add_to_queue(fp, dict(meta))
                except Exception:
                    pass
            if self._audio.playlist:
                fp, meta = self._audio.playlist[0]
                self._audio.play_song(fp, meta)
                self._player.set_track(
                    meta.get("title",  os.path.basename(fp)),
                    meta.get("artist", "Unknown Artist"),
                    int((meta.get("duration", 0) or 0) * 1000),
                )
                self._player.set_playing(True)
        except Exception as exc:
            print(f"[DesktopApp] play_playlist error: {exc}")

    def _on_playback_state(self, playing: bool):
        self._player.set_playing(playing)

    def _on_position_changed(self, position_ms: int):
        self._player.update_position(position_ms)

    def _on_shuffle(self, enabled: bool):
        self._audio.shuffle_mode = enabled
        self._audio.update_shuffle_button_style()

    def _on_repeat(self, enabled: bool):
        self._audio.repeat_mode = 1 if enabled else 0
        self._audio.update_repeat_button_style()

    @pyqtSlot(str)
    def _on_artist_clicked(self, artist_name: str):
        if artist_name:
            self._discover_page._search_input.setText(artist_name)
            self._on_search(artist_name)

    # ── sidebar library ────────────────────────────────────────

    def _load_sidebar_library(self):
        try:
            path = config.get_download_path()
            if not os.path.isdir(path):
                return
            folders = sorted(
                d for d in os.listdir(path)
                if os.path.isdir(os.path.join(path, d))
                and not d.startswith(".")
            )
            self._sidebar.populate_library(folders)
        except Exception as exc:
            print(f"[DesktopApp] sidebar library error: {exc}")

    # ── metadata check ─────────────────────────────────────────

    def _check_metadata(self):
        if config.get("ignore_metadata_fix", False):
            return
        try:
            from app.desktop.utils.metadata import scan_for_metadata_issues
            issues = scan_for_metadata_issues(config.get_download_path())
            if issues:
                FixMetadataDialog(issues, self).exec_()
        except Exception:
            pass

    # ── tray ───────────────────────────────────────────────────

    def _setup_tray(self):
        try:
            self._tray = QSystemTrayIcon(_make_tray_icon(), self)
            menu = QMenu()
            menu.addAction(QAction("Show", self, triggered=self.show))
            menu.addAction(QAction("Quit", self,
                                   triggered=QApplication.quit))
            self._tray.setContextMenu(menu)
            self._tray.setToolTip("ñusic")
            self._tray.show()
        except Exception as exc:
            print(f"[Tray] {exc}")

    # ── close ──────────────────────────────────────────────────

    def closeEvent(self, event):
        config.set("window_size", [self.width(), self.height()])
        for t in (self._search_thread, self._album_thread):
            if t and t.isRunning():
                try:
                    t.stop()
                    t.quit()
                    t.wait(1000)
                except Exception:
                    pass
        event.accept()