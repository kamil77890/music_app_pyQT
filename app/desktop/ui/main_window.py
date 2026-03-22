"""
main_window.py — DesktopApp
────────────────────────────
• Home section removed — Playlists is the default landing page
• No push_local_playlists / set_local_playlists (removed completely)
• Right panel hidden until first song plays
• browse_track_play_requested wired
• refresh_requested wired to recommender
• Thread stop() called with wait() before replacing to prevent "QThread destroyed while running"
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Dict, Optional

log = logging.getLogger(__name__)

from PyQt5.QtCore import Qt, QTimer, pyqtSlot, pyqtSignal, QEvent
from PyQt5.QtGui import QPainter, QColor, QIcon, QFont, QPixmap, QKeySequence
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QSplitter, QStackedWidget, QScrollArea,
    QApplication, QSystemTrayIcon, QMenu, QAction, QSizePolicy,
    QShortcut,
)

from app.desktop.ui.new_styles                      import get_stylesheet
from app.desktop.ui.widgets.main_dashboard          import MainDashboard
from app.desktop.ui.widgets.playback_controller     import PlaybackController
from app.desktop.ui.widgets.bottom_player_bar      import BottomNowPlayingBar
from app.desktop.ui.pages.playlists_page            import PlaylistsPage
from app.desktop.threads.search_thread              import SearchThread, AlbumTracksThread
from app.desktop.ui.dialogs.download_manager_dialog import DownloadManagerDialog
from app.desktop.ui.dialogs.fix_metadata_dialog     import FixMetadataDialog
from app.desktop.config                             import config
from app.desktop.ui.widgets.audio_player            import AudioPlayerWidget
from app.desktop.utils.helpers                      import song_to_dict, duration_to_ms
from app.desktop.utils.metadata                   import load_cover_pixmap_from_file
from app.desktop.utils.playlist_manager            import PlaylistManager

from PyQt5.QtWidgets import QMessageBox, QApplication

PAGE_DISCOVER  = 0
PAGE_PLAYLISTS = 1

_SIDEBAR_W = 252
_RIGHT_PANEL_MAX_W = 310
_MIN_CENTER_W = 180


def _cover_pixmap_for_track(
    file_path: str, is_url: bool, metadata: dict,
) -> Optional[QPixmap]:
    """Embedded art from file, else optional base64 from metadata dict."""
    cover_px: Optional[QPixmap] = None
    if not is_url and file_path and os.path.isfile(file_path):
        cover_px = load_cover_pixmap_from_file(file_path)
    if cover_px is None and metadata.get("cover_base64"):
        try:
            raw = base64.b64decode(metadata["cover_base64"])
            pm = QPixmap()
            if pm.loadFromData(raw) and not pm.isNull():
                cover_px = pm
        except Exception:
            pass
    return cover_px


def _norm_path_key(path: str) -> str:
    try:
        return os.path.normcase(os.path.normpath(path))
    except OSError:
        return path or ""


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
    p.drawText(0, 0, 32, 32, Qt.AlignCenter, "M")
    p.end()
    return QIcon(px)


# ─────────────────────────────────────────────────────────────────
#  Sidebar nav row
# ─────────────────────────────────────────────────────────────────
class _NavItem(QFrame):
    """Single sidebar navigation row with icon, title, optional subtitle."""
    clicked = pyqtSignal()

    def __init__(self, icon: str, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("nav_item")
        self.setCursor(Qt.PointingHandCursor)
        self.setFrameShape(QFrame.NoFrame)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 8, 14, 8)
        lay.setSpacing(12)
        ic = QLabel(icon)
        ic.setObjectName("nav_item_icon")
        ic.setFixedWidth(22)
        ic.setAlignment(Qt.AlignCenter)
        lay.addWidget(ic)
        col = QVBoxLayout()
        col.setSpacing(1)
        col.setContentsMargins(0, 0, 0, 0)
        t = QLabel(title)
        t.setObjectName("nav_item_title")
        col.addWidget(t)
        if subtitle:
            s = QLabel(subtitle)
            s.setObjectName("nav_item_sub")
            col.addWidget(s)
        lay.addLayout(col, 1)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(ev)


def _sidebar_divider() -> QFrame:
    d = QFrame()
    d.setFixedHeight(1)
    d.setObjectName("sidebar_divider")
    return d


# ─────────────────────────────────────────────────────────────────
#  Sidebar
# ─────────────────────────────────────────────────────────────────
class _Sidebar(QFrame):
    copy_cloud_url_clicked = pyqtSignal()
    fix_metadata_clicked   = pyqtSignal()
    library_item_clicked   = pyqtSignal(str)  # folder_path

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(252)
        self._nav_buttons: Dict[str, _NavItem] = {}
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Logo ──────────────────────────────────────────────
        logo_frame = QFrame()
        logo_frame.setFixedHeight(52)
        logo_frame.setStyleSheet("background:transparent;")
        ll = QHBoxLayout(logo_frame)
        ll.setContentsMargins(20, 6, 16, 6)
        logo = QLabel(
            "<span style='color:#4d59fb;font-size:24px;font-weight:900;letter-spacing:-0.5px;'>M</span>"
            "<span style='color:#e8eaf0;font-size:24px;font-weight:900;letter-spacing:-0.5px;'>usic</span>"
        )
        logo.setTextFormat(Qt.RichText)
        logo.setStyleSheet("background:transparent;")
        ll.addWidget(logo)
        ll.addStretch()
        root.addWidget(logo_frame)

        root.addWidget(_sidebar_divider())

        # ── Navigation ────────────────────────────────────────
        nav = QWidget()
        nav.setStyleSheet("background:transparent;")
        nlay = QVBoxLayout(nav)
        nlay.setContentsMargins(8, 8, 8, 4)
        nlay.setSpacing(2)

        for icon, label, sub, key in [
            ("🔍", "Discover", "Search & recommendations", "discover"),
            ("📚", "Playlists", "Your library", "playlists"),
        ]:
            btn = _NavItem(icon, label, sub)
            btn.clicked.connect(lambda k=key: self._on_nav(k))
            nlay.addWidget(btn)
            self._nav_buttons[key] = btn

        root.addWidget(nav)
        root.addWidget(_sidebar_divider())

        # ── Library list (scrollable) ─────────────────────────
        lib_hdr = QWidget()
        lib_hdr.setStyleSheet("background:transparent;")
        lh = QHBoxLayout(lib_hdr)
        lh.setContentsMargins(18, 12, 18, 6)
        lh.setSpacing(6)
        lib_title = QLabel("YOUR LIBRARY")
        lib_title.setObjectName("sidebar_section")
        self._library_count_lbl = QLabel("")
        self._library_count_lbl.setObjectName("sidebar_lib_count")
        lh.addWidget(lib_title)
        lh.addStretch()
        lh.addWidget(self._library_count_lbl)
        root.addWidget(lib_hdr)

        lib_scroll = QScrollArea()
        lib_scroll.setWidgetResizable(True)
        lib_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        lib_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        lib_scroll.setFrameShape(QFrame.NoFrame)
        lib_scroll.setObjectName("sidebar_scroll")

        self._library_widget = QWidget()
        self._library_widget.setStyleSheet("background:transparent;")
        self._library_lay = QVBoxLayout(self._library_widget)
        self._library_lay.setContentsMargins(8, 0, 8, 8)
        self._library_lay.setSpacing(2)
        self._library_lay.addStretch()
        lib_scroll.setWidget(self._library_widget)
        root.addWidget(lib_scroll, 1)

        root.addWidget(_sidebar_divider())

        # ── Bottom actions (always above app-wide mini player) ─
        bottom = QWidget()
        bottom.setStyleSheet("background:transparent;")
        blay = QVBoxLayout(bottom)
        blay.setContentsMargins(8, 8, 8, 10)
        blay.setSpacing(2)

        upload_btn = _NavItem("☁️", "Upload to Cloud", "Backblaze B2")
        upload_btn.clicked.connect(lambda: self._on_nav("upload"))
        blay.addWidget(upload_btn)
        self._nav_buttons["upload"] = upload_btn

        copy_btn = _NavItem("📋", "Copy Cloud URL")
        copy_btn.clicked.connect(self.copy_cloud_url_clicked.emit)
        blay.addWidget(copy_btn)

        fix_btn = _NavItem("🔧", "Fix Metadata", "Title, artist & covers")
        fix_btn.clicked.connect(self.fix_metadata_clicked.emit)
        blay.addWidget(fix_btn)

        root.addWidget(bottom)

    # ── helpers ────────────────────────────────────────────────

    def _on_nav(self, key: str):
        for k, btn in self._nav_buttons.items():
            btn.setProperty("active", "true" if k == key else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def set_active(self, key: str):
        self._on_nav(key)

    def populate_library(self, folders: list):
        """
        folders — list of (display_name, folder_path) tuples.
        Clicking a row emits library_item_clicked(folder_path).
        """
        while self._library_lay.count():
            item = self._library_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        n = len(folders)
        if n == 0:
            self._library_count_lbl.setText("")
            hint = QLabel(
                "Download music or create playlists to build your library."
            )
            hint.setObjectName("sidebar_empty_hint")
            hint.setWordWrap(True)
            self._library_lay.addWidget(hint)
            self._library_lay.addStretch()
            return

        self._library_count_lbl.setText(f"{n}")
        for name, folder_path in folders[:20]:
            row = QFrame()
            row.setObjectName("sidebar_lib_row")
            row.setCursor(Qt.PointingHandCursor)
            rl = QHBoxLayout(row)
            rl.setContentsMargins(12, 6, 12, 6)
            rl.setSpacing(10)
            icon = QLabel("📁")
            icon.setObjectName("sidebar_lib_icon")
            icon.setFixedWidth(18)
            icon.setAlignment(Qt.AlignCenter)
            rl.addWidget(icon)
            lbl = QLabel(name)
            lbl.setObjectName("sidebar_lib_label")
            lbl.setWordWrap(False)
            lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            rl.addWidget(lbl, 1)
            # clicking the row opens that playlist
            row.mousePressEvent = (
                lambda ev, fp=folder_path:
                self.library_item_clicked.emit(fp)
                if ev.button() == Qt.LeftButton else None
            )
            self._library_lay.addWidget(row)

        self._library_lay.addStretch()


# ─────────────────────────────────────────────────────────────────
#  DesktopApp
# ─────────────────────────────────────────────────────────────────
class DesktopApp(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Music")
        # Bez paska tytułu (bez „Music”, zamykania, minimalizacji)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)

        self._search_thread:      Optional[SearchThread]     = None
        self._album_thread:       Optional[AlbumTracksThread] = None
        self._recommender_thread                             = None
        self._current_page        = "discover"
        self._right_panel_visible = False
        self._initial_rec_done    = False
        self._artist_only_search  = False

        w, h = config.get("window_size", [1440, 900])
        self.setFixedSize(int(w), int(h))

        self._audio = AudioPlayerWidget()
        self._audio.playback_state_changed.connect(self._on_playback_state)
        self._audio.track_changed.connect(self._update_now_playing_ui)
        self._audio.player.positionChanged.connect(self._on_position_changed)
        self._audio.player.durationChanged.connect(self._on_player_duration_changed)
        self._hide_bottom_bar_timer = QTimer(self)
        self._hide_bottom_bar_timer.setSingleShot(True)
        self._hide_bottom_bar_timer.setInterval(280)
        self._hide_bottom_bar_timer.timeout.connect(self._hide_bottom_bar_if_still_stopped)

        self.setStyleSheet(
            get_stylesheet()
            + "\nQMainWindow { background-color: #000000; }\n")
        self._build_ui()
        self._setup_tray()

        # Playlists (library + «All Songs») is the default landing page
        self._switch_page("playlists")

        QTimer.singleShot(400,  self._load_sidebar_library)
        QTimer.singleShot(500,  self._load_daily_artists_from_library)
        QTimer.singleShot(900,  self._run_initial_recommendations)
        QTimer.singleShot(1200, self._check_metadata)

        self.show()
        self._center_window()

        self._quota_timer = QTimer(self)
        self._quota_timer.setInterval(30_000)
        self._quota_timer.timeout.connect(self._check_quota_status)
        self._quota_timer.start()

        self._setup_shortcuts()
        self._global_hotkeys_stop = None
        self._setup_global_hotkeys()

    def _center_window(self):
        screen = QApplication.primaryScreen().geometry()
        g = self.geometry()
        self.move(
            (screen.width()  - g.width())  // 2,
            (screen.height() - g.height()) // 2,
        )

    def _check_quota_status(self):
        from app.utils.api_key_manager import api_key_manager
        self._quota_banner.setVisible(api_key_manager.is_quota_exhausted)

    def _setup_shortcuts(self):
        from PyQt5.QtWidgets import QShortcut
        from PyQt5.QtGui import QKeySequence

        ctx = Qt.ApplicationShortcut

        def _sc(seq, slot):
            s = QShortcut(QKeySequence(seq), self)
            s.setContext(ctx)
            s.activated.connect(slot)

        _sc("Space", self._audio.toggle_play)
        _sc("Ctrl+Right", self._audio.next_song)
        _sc("Ctrl+Left", self._audio.previous_song)
        _sc("Ctrl+F", self._focus_search)
        _sc("Ctrl+1", lambda: self._switch_page("discover"))
        _sc("Ctrl+2", lambda: self._switch_page("playlists"))
        # * w oknie: play/pause (jak globalnie); wyciszenie: Ctrl+M
        _sc("Shift+8", self._audio.toggle_play)
        _sc(Qt.Key_Asterisk, self._audio.toggle_play)
        _sc("Ctrl+M", self._on_bottom_mute_toggle)
        # Skróty „. / ← / →” (mute / prev / next) tylko w global_hotkeys (pynput).

    def _setup_global_hotkeys(self) -> None:
        try:
            from app.desktop.utils.global_hotkeys import start_global_hotkeys
        except ImportError:
            return
        self._global_hotkeys_stop = start_global_hotkeys(
            on_play_pause=self._audio.toggle_play,
            on_next=self._audio.next_song,
            on_previous=self._audio.previous_song,
            on_mute=self._on_bottom_mute_toggle,
        )

    def changeEvent(self, event):
        # Minimalizacja → ukryj okno, aplikacja zostaje w zasobniku
        if event.type() == QEvent.WindowStateChange:
            if self.windowState() & Qt.WindowMinimized:
                QTimer.singleShot(0, self.hide)
        super().changeEvent(event)

    def _focus_search(self):
        self._switch_page("discover")
        self._discover_page._search_input.setFocus()
        self._discover_page._search_input.selectAll()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_splitter_layout()

    # ── UI build ───────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._splitter = QSplitter(Qt.Horizontal)
        self._splitter.setHandleWidth(1)
        self._splitter.setStyleSheet("QSplitter::handle{background:#141424;}")

        # Sidebar
        self._sidebar = _Sidebar()
        self._sidebar._nav_buttons["discover"].clicked.connect(
            lambda: self._switch_page("discover"))
        self._sidebar._nav_buttons["playlists"].clicked.connect(
            lambda: self._switch_page("playlists"))
        self._sidebar._nav_buttons["upload"].clicked.connect(self._start_b2_upload)
        self._sidebar.copy_cloud_url_clicked.connect(self._on_copy_cloud_music_url)
        self._sidebar.fix_metadata_clicked.connect(
            lambda: self._open_metadata_fixer(auto=False))
        self._sidebar.library_item_clicked.connect(self._on_sidebar_playlist_clicked)

        self._splitter.addWidget(self._sidebar)

        # Centre stack
        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background:#000000;")

        # PAGE_DISCOVER = 0
        self._discover_page = MainDashboard()
        self._discover_page.search_submitted.connect(self._on_search)
        self._discover_page.song_card_double_clicked.connect(self._play_song)
        self._discover_page.song_card_download_clicked.connect(self._download_single)
        self._discover_page.download_selected_clicked.connect(self._download_songs)
        self._discover_page.download_all_clicked.connect(self._download_songs)
        self._discover_page.album_clicked.connect(self._on_album_clicked)
        self._discover_page.artist_clicked.connect(self._on_artist_clicked)
        self._discover_page.refresh_requested.connect(self._on_refresh_recommendations)
        self._stack.addWidget(self._discover_page)

        # PAGE_PLAYLISTS = 1
        self._playlists_page = PlaylistsPage()
        self._playlists_page.playlist_play_requested.connect(self._play_playlist)
        self._playlists_page.playlist_random_requested.connect(
            self._play_random_from_playlist)
        self._playlists_page.song_play_requested.connect(self._play_song)
        self._stack.addWidget(self._playlists_page)

        self._splitter.addWidget(self._stack)

        # Right column — album / playlist tracks only
        self._player = PlaybackController()
        self._player.browse_track_play_requested.connect(self._play_song)
        self._player.browse_track_download_requested.connect(self._download_single)
        self._player.download_all_album_requested.connect(
            self._download_album_as_playlist)
        self._player.album_panel_closed.connect(self._on_album_panel_closed)
        self._splitter.addWidget(self._player)

        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setStretchFactor(2, 0)

        self._splitter.setCollapsible(0, False)
        self._splitter.setCollapsible(2, True)
        self._player.setVisible(False)
        QTimer.singleShot(0, self._apply_splitter_layout)

        root.addWidget(self._splitter, 1)

        # Quota exhausted banner (hidden by default)
        self._quota_banner = QFrame()
        self._quota_banner.setObjectName("quota_banner")
        self._quota_banner.setFixedHeight(40)
        self._quota_banner.setVisible(False)
        qb_lay = QHBoxLayout(self._quota_banner)
        qb_lay.setContentsMargins(20, 0, 20, 0)
        qb_lbl = QLabel("YouTube API quota exhausted on all keys — search and metadata features are temporarily unavailable.")
        qb_lbl.setStyleSheet("color:#f0b429;font-size:12px;font-weight:600;background:transparent;")
        qb_lay.addWidget(qb_lbl)
        qb_lay.addStretch()
        qb_dismiss = QPushButton("✕")
        qb_dismiss.setFixedSize(24, 24)
        qb_dismiss.setStyleSheet("QPushButton{background:transparent;border:none;color:#f0b429;font-size:14px;}QPushButton:hover{color:#fff;}")
        qb_dismiss.clicked.connect(lambda: self._quota_banner.setVisible(False))
        qb_lay.addWidget(qb_dismiss)
        root.addWidget(self._quota_banner)

        # App-wide bottom mini player (full width, above hidden engine widget)
        self._bottom_player = BottomNowPlayingBar()
        self._bottom_player.play_pause_clicked.connect(self._audio.toggle_play)
        self._bottom_player.prev_clicked.connect(self._audio.previous_song)
        self._bottom_player.next_clicked.connect(self._audio.next_song)
        self._bottom_player.seek_requested.connect(
            lambda ms: self._audio.player.setPosition(ms))
        self._bottom_player.shuffle_clicked.connect(self._on_bottom_shuffle)
        self._bottom_player.repeat_clicked.connect(self._on_bottom_repeat)
        self._bottom_player.volume_changed.connect(self._on_bottom_volume_changed)
        self._bottom_player.mute_toggle_requested.connect(
            self._on_bottom_mute_toggle)
        root.addWidget(self._bottom_player)

        self._audio.setVisible(False)
        root.addWidget(self._audio)

        self.statusBar().hide()
        self.statusBar().setSizeGripEnabled(False)
        self._sync_bottom_volume_ui()
        self._refresh_transport_styles()
        self._bottom_player.setVisible(False)
        self._audio.player.stateChanged.connect(self._on_player_state_changed)

    def _on_player_state_changed(self, state) -> None:
        from PyQt5.QtMultimedia import QMediaPlayer
        if state in (QMediaPlayer.PlayingState, QMediaPlayer.PausedState):
            self._hide_bottom_bar_timer.stop()
            self._bottom_player.setVisible(True)
        elif state == QMediaPlayer.StoppedState:
            self._hide_bottom_bar_timer.start()

    def _hide_bottom_bar_if_still_stopped(self) -> None:
        from PyQt5.QtMultimedia import QMediaPlayer
        if self._audio.player.state() == QMediaPlayer.StoppedState:
            self._bottom_player.setVisible(False)

    def _on_player_duration_changed(self, duration_ms: int) -> None:
        if duration_ms and duration_ms > 0:
            self._bottom_player.set_duration_ms(duration_ms)

    def _apply_splitter_layout(self):
        """Keep sidebar + center + optional album panel; avoid negative/zero center width."""
        if not getattr(self, "_splitter", None):
            return
        w = max(self.width(), 400)
        inner = max(0, w - _SIDEBAR_W)
        if getattr(self, "_right_panel_visible", False):
            w_right = min(_RIGHT_PANEL_MAX_W, max(0, inner - _MIN_CENTER_W))
            w_center = max(_MIN_CENTER_W, inner - w_right)
            self._splitter.setSizes([_SIDEBAR_W, w_center, w_right])
        else:
            self._splitter.setSizes(
                [_SIDEBAR_W, max(_MIN_CENTER_W, inner), 0])

    def _show_right_panel(self) -> None:
        """Show album / playlist track list in the right column."""
        self._right_panel_visible = True
        self._player.setVisible(True)
        self._player.raise_()
        self._apply_splitter_layout()

    def _on_album_panel_closed(self):
        """User closed the album panel — collapse right column."""
        self._right_panel_visible = False
        self._player.setVisible(False)
        self._apply_splitter_layout()

    def _on_bottom_shuffle(self) -> None:
        self._audio.toggle_shuffle()
        self._refresh_transport_styles()

    def _on_bottom_repeat(self) -> None:
        self._audio.toggle_repeat()
        self._refresh_transport_styles()

    def _sync_bottom_volume_ui(self) -> None:
        a = self._audio
        self._bottom_player.set_volume_ui(
            a.player.volume(),
            a.is_muted,
            nominal_when_muted=a.previous_volume if a.is_muted else None,
        )

    def _on_bottom_volume_changed(self, value: int) -> None:
        self._audio.set_volume(value)
        self._sync_bottom_volume_ui()

    def _on_bottom_mute_toggle(self) -> None:
        self._audio.toggle_mute()
        self._sync_bottom_volume_ui()

    def _notify_status(self, msg: str, duration_ms: int = 8000) -> None:
        log.info("Status: %s", msg)
        tray = getattr(self, "_tray", None)
        if tray is not None:
            try:
                dm = duration_ms if duration_ms and duration_ms > 0 else 60000
                tray.showMessage("Music", msg, QSystemTrayIcon.Information, dm)
            except Exception:
                pass

    def _refresh_transport_styles(self) -> None:
        self._bottom_player.set_shuffle_style(self._audio.shuffle_mode)
        self._bottom_player.set_repeat_style(self._audio.repeat_mode)

    # ── page switching ─────────────────────────────────────────

    def _switch_page(self, key: str):
        self._current_page = key
        self._sidebar.set_active(key)
        if key == "discover":
            self._stack.setCurrentIndex(PAGE_DISCOVER)
        elif key == "playlists":
            self._stack.setCurrentIndex(PAGE_PLAYLISTS)
            self._playlists_page.refresh()

    # ── recommendations ────────────────────────────────────────

    def _run_initial_recommendations(self):
        if self._initial_rec_done:
            return
        try:
            from app.desktop.utils.recommendation_cache import try_load_cached_queries
        except ImportError:
            try_load_cached_queries = None  # type: ignore
        download_path = config.get_download_path()
        if try_load_cached_queries and os.path.isdir(download_path):
            cached = try_load_cached_queries(download_path)
            if cached:
                self._apply_recommendation_queries(cached, save_cache=False)
                return
        self._run_recommender(randomise=False)

    @pyqtSlot()
    def _on_refresh_recommendations(self):
        self._run_recommender(randomise=True)

    def _run_recommender(self, randomise: bool = False):
        try:
            from app.desktop.utils.recommender import RecommenderThread
        except ImportError:
            return

        download_path = config.get_download_path()
        if not os.path.isdir(download_path):
            return

        if self._recommender_thread and self._recommender_thread.isRunning():
            self._recommender_thread.stop()
            # Krótki wait() zostawiał wątek w tle → GC niszczył QThread → "Destroyed while still running"
            self._recommender_thread.wait(120_000)

        self._discover_page.show_loading("Building recommendations from your library…")

        self._recommender_thread = RecommenderThread(
            download_path=download_path,
            max_results=10,
            randomise=randomise,
        )
        self._recommender_thread.recommendations_ready.connect(
            self._on_recommendations_ready_from_thread)
        self._recommender_thread.error.connect(
            lambda e: log.error("Recommender error: %s", e))
        self._recommender_thread.start()

    @pyqtSlot(list, int)
    def _on_recommendations_ready_from_thread(self, queries: list, library_song_count: int):
        self._apply_recommendation_queries(queries, save_cache=True, library_song_count=library_song_count)

    def _apply_recommendation_queries(
        self,
        queries: list,
        *,
        save_cache: bool,
        library_song_count: int = 0,
    ) -> None:
        self._initial_rec_done = True
        if not queries:
            self._discover_page.show_loading(
                "Download some music first — your recommendations will appear here.")
            return
        if save_cache:
            try:
                from app.desktop.utils.recommendation_cache import save_cached_queries
                save_cached_queries(
                    config.get_download_path(), queries, library_song_count)
            except Exception as exc:
                log.debug("Recommendation cache save: %s", exc)
        self._on_search(queries[0])

    # ── search ─────────────────────────────────────────────────

    @pyqtSlot(str)
    def _on_search(self, query: str, artist_only: bool = False):
        if not query.strip():
            return

        self._artist_only_search = artist_only

        # Stop previous search and wait until it exits (short waits caused
        # "QThread: Destroyed while thread is still running" when starting a new search).
        if self._search_thread is not None:
            self._search_thread.stop()
            if self._search_thread.isRunning():
                self._search_thread.wait(120_000)

        self._discover_page.show_loading(f'Searching "{query}"…')
        self._stack.setCurrentIndex(PAGE_DISCOVER)
        self._sidebar.set_active("discover")
        self._current_page = "discover"

        self._search_thread = SearchThread(query=query, max_results=20, parent=self)
        self._search_thread.results_ready.connect(self._on_search_results)
        self._search_thread.error.connect(
            lambda e: self._discover_page.show_loading(f"Search error: {e}"))
        self._search_thread.start()

    @pyqtSlot(list, list, list, str)
    def _on_search_results(self, songs, albums, playlists, _):
        af = None
        if self._artist_only_search:
            af = self._discover_page.get_search_text().strip() or None
        self._discover_page.set_search_results(
            songs, albums, playlists, artist_filter=af)

    # ── album expansion ────────────────────────────────────────

    @pyqtSlot(str)
    def _on_album_clicked(self, playlist_id: str):
        if not playlist_id or not str(playlist_id).strip():
            log.warning("Album click ignored: empty playlist_id")
            return

        if self._album_thread is not None:
            self._album_thread.stop()
            if self._album_thread.isRunning():
                self._album_thread.wait(60_000)

        self._show_right_panel()
        if hasattr(self._player, "show_album_browse_loading"):
            self._player.show_album_browse_loading()

        self._album_thread = AlbumTracksThread(playlist_id=playlist_id, parent=self)
        self._album_thread.tracks_ready.connect(self._on_album_tracks_ready)
        self._album_thread.error.connect(lambda e: log.error("Album track fetch error: %s", e))
        self._album_thread.start()

    @pyqtSlot(str, list)
    def _on_album_tracks_ready(self, playlist_id: str, tracks: list):
        self._discover_page.update_album_card_tracks(playlist_id, tracks)
        if hasattr(self._player, "show_album_browse"):
            self._player.show_album_browse(playlist_id, tracks)

    # ── download ───────────────────────────────────────────────

    def _normalise_songs(self, songs: list) -> list:
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
        self._download_songs(self._normalise_songs([entry]))

    def _download_songs(self, songs: list):
        clean = self._normalise_songs(songs)
        if not clean:
            return
        dlg = DownloadManagerDialog(
            songs=clean,
            download_path=config.get_download_path(),
            parent=self,
        )
        dlg.download_finished.connect(self._on_download_done)
        dlg.show()

    def _download_album_as_playlist(self, tracks: list):
        """Download all tracks from an album browse panel and auto-create a playlist."""
        clean = self._normalise_songs(tracks)
        if not clean:
            return
        album_name = ""
        if clean:
            album_name = (clean[0].get("album") or
                          clean[0].get("playlist_title") or
                          clean[0].get("title", "Album"))
        dlg = DownloadManagerDialog(
            songs=clean,
            download_path=config.get_download_path(),
            parent=self,
        )
        dlg._pl_check.setChecked(True)
        dlg._pl_name.setText(album_name)
        dlg._pl_name.setVisible(True)
        dlg.download_finished.connect(self._on_download_done)
        dlg.show()

    @pyqtSlot(str)
    def _on_download_done(self, playlist_name: str):
        QTimer.singleShot(400, self._load_sidebar_library)
        QTimer.singleShot(500, self._load_daily_artists_from_library)
        QTimer.singleShot(600, self._sync_auto_playlist)
        if self._current_page == "playlists":
            QTimer.singleShot(800, self._playlists_page.refresh)

    def _sync_auto_playlist(self):
        try:
            from app.desktop.utils.auto_playlist import get_auto_playlist_manager
            mgr   = get_auto_playlist_manager(config.get_download_path())
            added = mgr.sync_from_library(config.get_download_path())
            if added:
                log.info("Synced %d new song(s) to auto-playlist", added)
        except Exception as exc:
            log.error("_sync_auto_playlist: %s", exc)

    # ── playback ───────────────────────────────────────────────

    def _update_now_playing_ui(self, file_path: str, metadata: dict) -> None:
        """Synchronizuje dolny pasek z faktycznie odtwarzanym utworem (next/prev/kolejka)."""
        if not file_path:
            return
        is_url = isinstance(file_path, str) and file_path.startswith(
            ("http://", "https://"))
        meta = dict(metadata) if metadata else {}
        for fp, m in self._audio.playlist:
            if fp == file_path:
                merged = dict(m)
                merged.update(meta)
                meta = merged
                break
        title = meta.get("title", os.path.basename(file_path))
        artist = meta.get("artist", "Unknown Artist")
        dur_ms = duration_to_ms(meta.get("duration", 0))
        cover = (
            meta.get("high_res_thumbnail")
            or meta.get("thumbnail")
            or meta.get("cover")
            or ""
        )
        cover_px = _cover_pixmap_for_track(file_path, is_url, meta)
        self._hide_bottom_bar_timer.stop()
        self._bottom_player.setVisible(True)
        self._bottom_player.set_track(
            title, artist, dur_ms, cover_url=cover, pixmap=cover_px)
        self._bottom_player.set_playing(True)

    def _play_song(self, file_path: str, metadata: dict):
        is_url = isinstance(file_path, str) and file_path.startswith(
            ("http://", "https://"))
        if not file_path:
            return
        if not is_url and not os.path.exists(file_path):
            return
        # YouTube pages are HTML — Qt cannot stream them; avoid GStreamer errors
        if is_url and (
            "youtube.com/watch" in file_path
            or "youtu.be/" in file_path
        ):
            log.info(
                "Skipping YouTube URL playback (download to library first): %s",
                file_path[:80],
            )
            return
        try:
            already = any(fp == file_path for fp, _ in self._audio.playlist)
            if not already:
                self._audio.add_to_playlist(file_path, metadata)
            self._audio.play_song(file_path, metadata)
            self._audio.current_playlist = list(self._audio.playlist)
            # UI „now playing” aktualizuje sygnał track_changed → _update_now_playing_ui
            folder = metadata.get("from_playlist_folder")
            if folder and os.path.isdir(folder):
                self._fill_queue_random_from_playlist(folder, file_path)
        except Exception as exc:
            log.error("_play_song: %s", exc)

    def play_song_from_manager(self, file_path: str, metadata: dict):
        self._play_song(file_path, metadata)

    def _play_playlist(self, folder_path: str):
        try:
            from app.desktop.utils.helpers import get_mp3_files_recursive
            from app.desktop.utils.metadata import get_audio_metadata

            files = get_mp3_files_recursive(folder_path)
            if not files:
                return
            pairs = []
            for fp in files:
                try:
                    meta = get_audio_metadata(fp)
                    m = dict(meta)
                    m["from_playlist_folder"] = folder_path
                    pairs.append((fp, m))
                except Exception:
                    pass
            if not pairs:
                return
            self._audio.replace_playlist(pairs)
            fp, meta = pairs[0]
            self._audio.play_song(fp, meta)
            self._hide_bottom_bar_timer.stop()
            self._bottom_player.setVisible(True)
            if self._player.is_browse_open() and not self._right_panel_visible:
                self._show_right_panel()
            # track_changed → _update_now_playing_ui
        except Exception as exc:
            log.error("_play_playlist: %s", exc)

    def _play_random_from_playlist(self, folder_path: str):
        """Pick one random track from the playlist folder and play it."""
        import random
        try:
            from app.desktop.utils.helpers import get_mp3_files_recursive
            from app.desktop.utils.metadata import get_audio_metadata
        except ImportError:
            return
        try:
            files = [f for f in get_mp3_files_recursive(folder_path) if os.path.isfile(f)]
            if not files:
                QMessageBox.information(
                    self, "Playlist", "No audio files found in this playlist.")
                return
            pairs = []
            for fp in files:
                try:
                    meta = get_audio_metadata(fp)
                    m = dict(meta)
                    m["from_playlist_folder"] = folder_path
                    pairs.append((fp, m))
                except Exception:
                    pass
            if not pairs:
                return
            self._audio.replace_playlist(pairs)
            i = random.randrange(len(pairs))
            fp, meta = pairs[i]
            self._audio.current_index = i
            self._audio.play_song(fp, meta)
            self._hide_bottom_bar_timer.stop()
            self._bottom_player.setVisible(True)
            # track_changed → _update_now_playing_ui
        except Exception as exc:
            log.error("_play_random_from_playlist: %s", exc)

    def _fill_queue_random_from_playlist(self, folder_path: str, current_fp: str):
        """Append shuffled other tracks from the same playlist (no duplicates)."""
        import random
        try:
            from app.desktop.utils.metadata import get_audio_metadata
        except ImportError:
            return
        try:
            data = PlaylistManager.get_playlist_info(folder_path)
        except Exception:
            return
        cur_k = _norm_path_key(current_fp)
        existing = {_norm_path_key(fp) for fp, _ in self._audio.playlist}
        candidates = []
        for s in data.get("songs", []):
            fp = s.get("file_path", "")
            if not fp or not os.path.isfile(fp):
                continue
            nk = _norm_path_key(fp)
            if nk == cur_k or nk in existing:
                continue
            try:
                m = get_audio_metadata(fp)
                candidates.append((fp, dict(m)))
            except Exception:
                pass
        random.shuffle(candidates)
        for fp, meta in candidates:
            nk = _norm_path_key(fp)
            if nk in existing:
                continue
            if any(nk == _norm_path_key(x[0]) for x in self._audio.playlist):
                continue
            self._audio.add_to_playlist(fp, meta)
            existing.add(nk)
        self._audio.current_playlist = list(self._audio.playlist)

    def _on_playback_state(self, playing: bool):
        self._bottom_player.set_playing(playing)

    def _on_position_changed(self, position_ms: int):
        self._bottom_player.update_position(position_ms)

    @pyqtSlot(str)
    def _on_artist_clicked(self, artist_name: str):
        if artist_name:
            self._discover_page._search_input.setText(artist_name)
            self._on_search(artist_name, artist_only=True)

    # ── Daily Artists (from local library) ───────────────────

    def _load_daily_artists_from_library(self):
        try:
            from app.desktop.utils.library_artists import get_top_artists_from_library
        except ImportError:
            return
        path = config.get_download_path()
        if not os.path.isdir(path):
            return
        artists = get_top_artists_from_library(path, min_songs=3, max_artists=7)
        if artists:
            self._discover_page.set_daily_artists_from_library(artists)

    def _on_copy_cloud_music_url(self):
        try:
            from app.desktop.utils.cloud_client import public_music_url_for_clipboard
        except ImportError:
            QMessageBox.warning(self, "Error", "cloud_client not available.")
            return
        url = public_music_url_for_clipboard()
        if url:
            QApplication.clipboard().setText(url)
            QMessageBox.information(
                self, "Copied",
                "Public music folder URL copied to clipboard.\n\n"
                f"{url}")
        else:
            QMessageBox.warning(
                self, "Unavailable",
                "Could not load /cloud/config. Is the API server running on "
                f"{config.get('api_base_url', 'http://127.0.0.1:8001')} ?")

    # ── sidebar library ────────────────────────────────────────

    def _load_sidebar_library(self):
        try:
            path = config.get_download_path()
            if not os.path.isdir(path):
                return
            folders = sorted(
                (d, os.path.join(path, d))
                for d in os.listdir(path)
                if os.path.isdir(os.path.join(path, d))
                and not d.startswith(".")
            )
            self._sidebar.populate_library(folders)
        except Exception as exc:
            log.error("Sidebar load error: %s", exc)

    def _on_sidebar_playlist_clicked(self, folder_path: str):
        """Open the Playlists tab and immediately show the selected playlist."""
        self._switch_page("playlists")
        # give the page a moment to refresh before pushing the detail view
        QTimer.singleShot(50, lambda: self._playlists_page.open_playlist(folder_path))

    # ── B2 cloud upload ──────────────────────────────────────────

    def _start_b2_upload(self):
        """Upload all music files via local API server (POST /cloud/upload)."""
        try:
            from app.desktop.utils.b2_uploader import B2UploadThread, collect_music_files
        except ImportError as exc:
            QMessageBox.warning(self, "Upload Error", str(exc))
            return

        music_dir = config.get_download_path()
        if not os.path.isdir(music_dir):
            QMessageBox.information(self, "No Music",
                                    "No music directory found. Download some songs first.")
            return

        files = collect_music_files(music_dir)
        if not files:
            QMessageBox.information(self, "No Music Files",
                                    "No audio files found to upload.")
            return

        reply = QMessageBox.question(
            self, "Upload to Cloud",
            f"Upload {len(files)} music file(s) to Backblaze B2?\n"
            f"This will run in the background.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
        )
        if reply != QMessageBox.Yes:
            return

        if hasattr(self, '_b2_thread') and self._b2_thread and self._b2_thread.isRunning():
            QMessageBox.information(self, "Upload in Progress",
                                    "An upload is already running.")
            return

        self._b2_thread = B2UploadThread(music_dir)
        self._b2_thread.progress.connect(self._on_b2_progress)
        self._b2_thread.file_done.connect(self._on_b2_file_done)
        self._b2_thread.upload_finished.connect(self._on_b2_finished)
        self._b2_thread.start()

        self._notify_status(
            f"Uploading {len(files)} file(s) to cloud…",
            15000,
        )

    def _on_b2_progress(self, current: int, total: int, filename: str):
        short = (filename or "")[:70]
        self._notify_status(f"Cloud upload {current}/{total}: {short}", 4000)

    def _on_b2_file_done(self, filepath: str, success: bool, message: str):
        if not success and filepath == "":
            QMessageBox.warning(self, "Upload Error", message)

    def _on_b2_finished(self, uploaded: int, failed: int):
        msg = f"Cloud upload finished: {uploaded} ok"
        if failed:
            msg += f", {failed} failed"
        self._notify_status(msg, 12000)

    # ── metadata check ─────────────────────────────────────────

    def _check_metadata(self):
        if config.get("ignore_metadata_fix", False):
            return
        self._open_metadata_fixer(auto=True)

    def _open_metadata_fixer(self, auto: bool = False):
        """Scan library and open the fix-metadata dialog.
        If `auto` is True, only show when there are issues; otherwise always scan."""
        try:
            from app.desktop.utils.metadata import scan_for_metadata_issues
            issues = scan_for_metadata_issues(config.get_download_path())
            if issues:
                FixMetadataDialog(issues, self).exec_()
            elif not auto:
                QMessageBox.information(
                    self, "Metadata",
                    "All songs have valid metadata — nothing to fix.")
        except Exception as exc:
            if not auto:
                QMessageBox.warning(
                    self, "Metadata scan error", str(exc))
            else:
                log.warning("Metadata scan: %s", exc)

    # ── tray ───────────────────────────────────────────────────

    def _show_main_window(self) -> None:
        self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

    def _setup_tray(self):
        try:
            self._tray = QSystemTrayIcon(_make_tray_icon(), self)
            menu = QMenu()
            menu.addAction(QAction("Show", self, triggered=self._show_main_window))
            menu.addAction(QAction("Quit", self, triggered=QApplication.quit))
            self._tray.setContextMenu(menu)
            self._tray.setToolTip("Music")
            self._tray.activated.connect(self._on_tray_activated)
            self._tray.show()
        except Exception as exc:
            log.warning("Tray icon setup: %s", exc)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self._show_main_window()

    # ── close ──────────────────────────────────────────────────

    def closeEvent(self, event):
        if getattr(self, "_global_hotkeys_stop", None):
            try:
                self._global_hotkeys_stop()
            except Exception:
                pass
            self._global_hotkeys_stop = None
        config.set("window_size", [self.width(), self.height()])
        threads = [self._search_thread, self._album_thread, self._recommender_thread]
        if hasattr(self, '_b2_thread'):
            threads.append(self._b2_thread)
        for t in threads:
            if t and t.isRunning():
                try:
                    t.stop()
                    t.quit()
                    t.wait(1000)
                except Exception:
                    pass
        event.accept()