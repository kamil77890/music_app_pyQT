# main_window.py - Fixed version with removed unused code
import os
import random
from typing import List, Optional, Dict, Any

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QFrame, QSystemTrayIcon, QMenu, QAction, QGridLayout,
    QApplication, QMainWindow, QFileDialog, QStackedWidget, QSizePolicy,
    QTabWidget, QMessageBox, QInputDialog, QCheckBox, QSplitter
)
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QLinearGradient, QBrush
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve

from app.desktop.config import config
from app.desktop.ui.widgets.song_card import SongCard
from app.desktop.ui.widgets.playlist_card import PlaylistCard
from app.desktop.ui.widgets.audio_player import AudioPlayerWidget
from app.desktop.ui.dialogs.settings_dialog import SettingsDialog
from app.desktop.ui.dialogs.progress_dialog import ProgressDialog
from app.desktop.ui.dialogs.create_playlist_dialog import CreatePlaylistDialog
from app.desktop.ui.dialogs.fix_metadata_dialog import FixMetadataDialog
from app.desktop.threads.preview_thread import PreviewThread
from app.desktop.threads.download_thread import DownloadThread
from app.desktop.utils.helpers import song_to_dict
from app.desktop.utils.metadata import get_audio_metadata
from app.desktop.utils.playlist_manager import PlaylistManager


class DesktopApp(QMainWindow):
    """Main application window with fixed issues and cleaned up code"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🎵 MusicFlow - Smart Music Player")
        
        # Color scheme
        self.colors = {
            'bg_dark': '#121212',
            'bg_light': '#181818',
            'bg_lighter': '#282828',
            'bg_hover': '#2A2A2A',
            'accent_green': '#1DB954',
            'accent_light': '#1ED760',
            'text_primary': '#FFFFFF',
            'text_secondary': '#B3B3B3',
            'text_disabled': '#535353',
        }
        
        # Window size
        w, h = config.get("window_size", [1400, 900])
        self.resize(w, h)
        self.setMinimumSize(1000, 700)
        
        # Initialize state variables (IMPORTANT: All must be initialized before use)
        self.preview_cards: List[SongCard] = []
        self.all_preview_songs: List[Dict] = []
        self.current_preview_thread: Optional[PreviewThread] = None
        self.download_thread: Optional[DownloadThread] = None
        self.playlist_cards: List[PlaylistCard] = []
        self.playlist_song_cards: List[SongCard] = []
        self.recently_song_cards: List[SongCard] = []
        self.current_library_tab: str = "Playlists"
        self.playlist_view_page: Optional[QWidget] = None
        
        # Search results
        self.search_results = {
            "songs": [],
            "playlists": [],
            "recommendations": []
        }
        
        # Audio player
        self.audio_player = AudioPlayerWidget()
        self.audio_player.playback_state_changed.connect(self.on_playback_state_changed)
        
        # Search timer for debouncing
        self.search_timer = QTimer()
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self.perform_search)
        
        # Central widget
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        # Apply stylesheet
        self.setStyleSheet(self.get_spotify_stylesheet())
        
        # Build UI
        self.build_ui()
        
        # Setup system tray
        self.setup_tray()
        
        # Load data with delays to prevent UI blocking
        QTimer.singleShot(500, self.load_library)
        QTimer.singleShot(1000, self.check_and_fix_metadata)
        QTimer.singleShot(100, self.apply_initial_animations)
        
        # Show window
        self.show()
        self.center_on_screen()
        
        # Start with library page
        self.switch_page("library", self.btn_library)
    
    def center_on_screen(self):
        """Center window on primary screen"""
        screen = QApplication.primaryScreen().geometry()
        size = self.geometry()
        self.move(
            (screen.width() - size.width()) // 2,
            (screen.height() - size.height()) // 2
        )
    
    def apply_initial_animations(self):
        """Apply fade-in animations to sidebar and main content"""
        for i in range(self.sidebar_layout.count()):
            widget = self.sidebar_layout.itemAt(i).widget()
            if widget:
                self.fade_in_widget(widget, delay=i*50)
        
        self.fade_in_widget(self.main_content, delay=300)
    
    def fade_in_widget(self, widget, duration=300, delay=0):
        """Fade in widget with animation"""
        if not widget:
            return
        
        widget.setGraphicsEffect(None)
        animation = QPropertyAnimation(widget, b"windowOpacity")
        animation.setDuration(duration)
        animation.setStartValue(0)
        animation.setEndValue(1)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        
        if delay > 0:
            QTimer.singleShot(delay, animation.start)
        else:
            animation.start()
    
    def build_ui(self):
        """Build main UI structure"""
        main_layout = QVBoxLayout(self.central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Top bar
        top_bar = self.create_top_bar()
        main_layout.addWidget(top_bar)
        
        # Content splitter (sidebar + main content)
        content_splitter = QSplitter(Qt.Horizontal)
        
        sidebar = self.create_sidebar()
        content_splitter.addWidget(sidebar)
        
        self.main_content = self.create_main_content()
        content_splitter.addWidget(self.main_content)
        
        content_splitter.setSizes([250, self.width() - 250])
        content_splitter.setHandleWidth(1)
        content_splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background-color: {self.colors['bg_lighter']};
                width: 1px;
            }}
        """)
        
        main_layout.addWidget(content_splitter, 1)
        
        # Audio player at bottom
        main_layout.addWidget(self.audio_player)
    
    def create_top_bar(self):
        """Create top navigation bar with search"""
        top_bar = QFrame()
        top_bar.setObjectName("top_bar")
        top_bar.setFixedHeight(60)
        
        layout = QHBoxLayout(top_bar)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(12)
        
        # Navigation buttons
        nav_layout = QHBoxLayout()
        nav_layout.setSpacing(8)
        
        back_btn = QPushButton("◀")
        back_btn.setObjectName("nav_btn")
        back_btn.setToolTip("Back")
        back_btn.clicked.connect(self.on_back)
        
        forward_btn = QPushButton("▶")
        forward_btn.setObjectName("nav_btn")
        forward_btn.setToolTip("Forward")
        forward_btn.clicked.connect(self.on_forward)
        
        nav_layout.addWidget(back_btn)
        nav_layout.addWidget(forward_btn)
        nav_layout.addSpacing(20)
        
        layout.addLayout(nav_layout)
        
        # Search input with enhanced styling
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Search songs, artists, playlists...")
        self.search_input.setMinimumWidth(400)
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {self.colors['bg_lighter']};
                border: 2px solid transparent;
                border-radius: 20px;
                padding: 10px 20px;
                color: {self.colors['text_primary']};
                font-size: 14px;
                selection-background-color: {self.colors['accent_green']};
                selection-color: #000000;
            }}
            QLineEdit:focus {{
                border: 2px solid {self.colors['accent_green']};
                background-color: {self.colors['bg_hover']};
            }}
            QLineEdit:hover {{
                border: 2px solid {self.colors['text_secondary']};
            }}
        """)
        
        # Connect search signals
        self.search_input.textChanged.connect(self.on_search_text_changed)
        self.search_input.returnPressed.connect(self.on_search_enter)
        
        layout.addWidget(self.search_input, 1)
        
        # User menu
        user_layout = QHBoxLayout()
        user_layout.setSpacing(12)
        
        upgrade_btn = QPushButton("Premium")
        upgrade_btn.setObjectName("user_btn")
        upgrade_btn.clicked.connect(self.show_upgrade_dialog)
        user_layout.addWidget(upgrade_btn)
        
        user_btn = QPushButton("👤 User")
        user_btn.setObjectName("user_btn")
        user_btn.setMenu(self.create_user_menu())
        user_layout.addWidget(user_btn)
        
        layout.addLayout(user_layout)
        
        return top_bar
    
    def create_sidebar(self):
        """Create sidebar with navigation and now playing"""
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(220)
        sidebar.setMaximumWidth(300)
        
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 16, 0, 16)
        layout.setSpacing(0)
        
        # Logo
        logo = QLabel("🎵 MusicFlow")
        logo.setStyleSheet(f"""
            color: {self.colors['accent_green']};
            font-size: 22px;
            font-weight: 800;
            padding: 0 16px 16px 16px;
            letter-spacing: -0.5px;
        """)
        layout.addWidget(logo)
        
        # Navigation buttons
        self.sidebar_layout = QVBoxLayout()
        self.sidebar_layout.setSpacing(4)
        
        self.btn_library = self.create_sidebar_button("📚 Your Library", "library", self.show_library)
        self.btn_search = self.create_sidebar_button("🔍 Search", "search", self.show_search)
        self.btn_discover = self.create_sidebar_button("🎵 Discover", "discover", self.show_discover)
        
        layout.addLayout(self.sidebar_layout)
        layout.addStretch()
        
        # Now Playing section
        now_playing_frame = QFrame()
        now_playing_frame.setStyleSheet(f"""
            background-color: {self.colors['bg_lighter']};
            border-radius: 8px;
            margin: 8px;
            padding: 12px;
        """)
        
        now_playing_layout = QVBoxLayout(now_playing_frame)
        
        now_playing_label = QLabel("Now Playing")
        now_playing_label.setStyleSheet(f"""
            color: {self.colors['text_secondary']};
            font-size: 12px;
            font-weight: 600;
            margin-bottom: 8px;
        """)
        now_playing_layout.addWidget(now_playing_label)
        
        self.sidebar_song_title = QLabel("No song playing")
        self.sidebar_song_title.setStyleSheet(f"""
            color: {self.colors['text_primary']};
            font-size: 14px;
            font-weight: 600;
        """)
        self.sidebar_song_title.setWordWrap(True)
        now_playing_layout.addWidget(self.sidebar_song_title)
        
        self.sidebar_song_artist = QLabel("")
        self.sidebar_song_artist.setStyleSheet(f"""
            color: {self.colors['text_secondary']};
            font-size: 12px;
        """)
        now_playing_layout.addWidget(self.sidebar_song_artist)
        
        layout.addWidget(now_playing_frame)
        
        return sidebar
    
    def create_sidebar_button(self, text, page_name, callback):
        """Create sidebar navigation button"""
        btn = QPushButton(text)
        btn.setObjectName("sidebar_btn")
        btn.clicked.connect(lambda: self.switch_page(page_name, btn))
        self.sidebar_layout.addWidget(btn)
        return btn
    
    def create_main_content(self):
        """Create main content area with stacked pages"""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        self.stacked_widget = QStackedWidget()
        
        # Create all pages
        self.search_page = self.create_search_page()
        self.stacked_widget.addWidget(self.search_page)
        
        self.library_page = self.create_library_page()
        self.stacked_widget.addWidget(self.library_page)
        
        self.discover_page = self.create_discover_page()
        self.stacked_widget.addWidget(self.discover_page)
        
        layout.addWidget(self.stacked_widget)
        
        return container
    
    
    def create_search_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(24)
        
        # Search header
        self.search_header = QWidget()
        header_layout = QHBoxLayout(self.search_header)
        
        self.search_label = QLabel("Search Music")
        self.search_label.setStyleSheet(f"""
            color: {self.colors['text_primary']};
            font-size: 28px;
            font-weight: 800;
        """)
        header_layout.addWidget(self.search_label)
        header_layout.addStretch()
        
        self.search_count = QLabel("")
        self.search_count.setStyleSheet(f"""
            color: {self.colors['text_secondary']};
            font-size: 14px;
        """)
        header_layout.addWidget(self.search_count)
        
        layout.addWidget(self.search_header)
        
        # Add spacing below tabs
        layout.addSpacing(16)
        
        # Search tabs
        self.search_tabs = QTabWidget()
        self.search_tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: none;
                background: transparent;
                margin-top: 12px;
            }}
            QTabBar::tab {{
                background: rgba(255, 255, 255, 0.05);
                color: {self.colors['text_secondary']};
                padding: 12px 24px;
                margin-right: 4px;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                font-size: 14px;
                font-weight: 600;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-bottom: none;
            }}
            QTabBar::tab:selected {{
                background: {self.colors['bg_lighter']};
                color: {self.colors['text_primary']};
                border: 1px solid {self.colors['accent_green']};
                border-bottom: none;
            }}
            QTabBar::tab:hover:!selected {{
                background: rgba(255, 255, 255, 0.08);
            }}
        """)
        
        # Songs tab
        self.search_songs_tab = QWidget()
        songs_layout = QVBoxLayout(self.search_songs_tab)
        songs_layout.setContentsMargins(0, 0, 0, 0)
        
        self.search_songs_scroll = QScrollArea()
        self.search_songs_scroll.setWidgetResizable(True)
        self.search_songs_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        self.search_songs_container = QWidget()
        self.search_songs_container.setObjectName("songs_container")
        
        self.search_songs_grid = QGridLayout(self.search_songs_container)
        self.search_songs_grid.setSpacing(16)
        self.search_songs_grid.setContentsMargins(0, 0, 0, 16)
        self.search_songs_grid.setAlignment(Qt.AlignTop)
        
        self.search_songs_scroll.setWidget(self.search_songs_container)
        songs_layout.addWidget(self.search_songs_scroll)
        
        # Playlists tab
        self.search_playlists_tab = QWidget()
        playlists_layout = QVBoxLayout(self.search_playlists_tab)
        playlists_layout.setContentsMargins(0, 0, 0, 0)
        
        self.search_playlists_scroll = QScrollArea()
        self.search_playlists_scroll.setWidgetResizable(True)
        self.search_playlists_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        self.search_playlists_container = QWidget()
        self.search_playlists_container.setObjectName("songs_container")
        
        self.search_playlists_grid = QGridLayout(self.search_playlists_container)
        self.search_playlists_grid.setSpacing(16)
        self.search_playlists_grid.setContentsMargins(0, 0, 0, 16)
        self.search_playlists_grid.setAlignment(Qt.AlignTop)
        
        self.search_playlists_scroll.setWidget(self.search_playlists_container)
        playlists_layout.addWidget(self.search_playlists_scroll)
        
        # Recommendations tab
        self.search_recommendations_tab = QWidget()
        rec_layout = QVBoxLayout(self.search_recommendations_tab)
        rec_layout.setContentsMargins(0, 0, 0, 0)
        
        self.recommendations_scroll = QScrollArea()
        self.recommendations_scroll.setWidgetResizable(True)
        self.recommendations_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        self.recommendations_container = QWidget()
        self.recommendations_container.setObjectName("songs_container")
        
        self.recommendations_grid = QGridLayout(self.recommendations_container)
        self.recommendations_grid.setSpacing(16)
        self.recommendations_grid.setContentsMargins(0, 0, 0, 16)
        self.recommendations_grid.setAlignment(Qt.AlignTop)
        
        self.recommendations_scroll.setWidget(self.recommendations_container)
        rec_layout.addWidget(self.recommendations_scroll)
        
        self.search_tabs.addTab(self.search_songs_tab, "Songs")
        self.search_tabs.addTab(self.search_playlists_tab, "Playlists")
        self.search_tabs.addTab(self.search_recommendations_tab, "Recommendations")
        
        layout.addWidget(self.search_tabs, 1)
        
        return page
    
    def create_library_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(24)
        
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        library_label = QLabel("Your Library")
        library_label.setStyleSheet(f"""
            color: {self.colors['text_primary']};
            font-size: 28px;
            font-weight: 800;
            margin-bottom: 8px;
        """)
        header_layout.addWidget(library_label)
        header_layout.addStretch()
        
        self.create_playlist_btn = QPushButton("+ New Playlist")
        self.create_playlist_btn.setObjectName("primary_btn")
        self.create_playlist_btn.setFixedWidth(150)
        self.create_playlist_btn.clicked.connect(self.create_new_playlist)
        header_layout.addWidget(self.create_playlist_btn)
        header_layout.addSpacing(10)
        
        self.library_search = QLineEdit()
        self.library_search.setPlaceholderText("Search playlists...")
        self.library_search.setFixedWidth(200)
        self.library_search.textChanged.connect(self.filter_playlists)
        header_layout.addWidget(self.library_search)
        
        layout.addWidget(header_widget)
        
        tabs_widget = QWidget()
        tabs_layout = QHBoxLayout(tabs_widget)
        tabs_layout.setSpacing(0)
        
        self.tab_buttons = {}
        tabs = ["Playlists", "Recently Added", "Artists", "Albums"]
        for tab in tabs:
            btn = QPushButton(tab)
            btn.setCheckable(True)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: {self.colors['text_secondary']};
                    border: none;
                    padding: 8px 16px;
                    font-size: 14px;
                    font-weight: 600;
                }}
                QPushButton:hover {{
                    color: {self.colors['text_primary']};
                }}
                QPushButton:checked {{
                    color: {self.colors['text_primary']};
                    border-bottom: 2px solid {self.colors['accent_green']};
                }}
            """)
            btn.clicked.connect(lambda checked, t=tab: self.switch_library_tab(t))
            tabs_layout.addWidget(btn)
            self.tab_buttons[tab] = btn
            if tab == "Playlists":
                btn.setChecked(True)
                self.current_library_tab = "Playlists"
        
        tabs_layout.addStretch()
        layout.addWidget(tabs_widget)
        
        self.library_content = QStackedWidget()
        
        self.playlists_tab = QWidget()
        playlists_layout = QVBoxLayout(self.playlists_tab)
        playlists_layout.setContentsMargins(0, 0, 0, 0)
        playlists_layout.setSpacing(16)
        
        playlists_header = QWidget()
        playlists_header_layout = QHBoxLayout(playlists_header)
        playlists_header_layout.setContentsMargins(0, 0, 0, 0)
        
        playlists_title = QLabel("All Playlists")
        playlists_title.setStyleSheet(f"""
            color: {self.colors['text_primary']};
            font-size: 18px;
            font-weight: 700;
        """)
        playlists_header_layout.addWidget(playlists_title)
        playlists_header_layout.addStretch()
        
        self.playlist_count = QLabel("0 playlists")
        self.playlist_count.setStyleSheet(f"""
            color: {self.colors['text_secondary']};
            font-size: 14px;
        """)
        playlists_header_layout.addWidget(self.playlist_count)
        
        playlists_layout.addWidget(playlists_header)
        
        self.playlists_scroll = QScrollArea()
        self.playlists_scroll.setWidgetResizable(True)
        self.playlists_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        self.playlists_container = QWidget()
        self.playlists_container.setObjectName("playlists_container")
        
        self.playlists_grid = QGridLayout(self.playlists_container)
        self.playlists_grid.setSpacing(16)
        self.playlists_grid.setContentsMargins(0, 0, 0, 16)
        self.playlists_grid.setAlignment(Qt.AlignTop)
        
        self.playlists_scroll.setWidget(self.playlists_container)
        playlists_layout.addWidget(self.playlists_scroll, 1)
        
        self.library_content.addWidget(self.playlists_tab)
        
        self.recently_tab = self.create_recently_added_tab()
        self.library_content.addWidget(self.recently_tab)
        
        self.artists_tab = self.create_artists_tab()
        self.library_content.addWidget(self.artists_tab)
        
        self.albums_tab = self.create_albums_tab()
        self.library_content.addWidget(self.albums_tab)
        
        layout.addWidget(self.library_content, 1)
        
        return page
    
    def create_recently_added_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        title = QLabel("Recently Added Songs")
        title.setStyleSheet(f"""
            color: {self.colors['text_primary']};
            font-size: 18px;
            font-weight: 700;
        """)
        header_layout.addWidget(title)
        header_layout.addStretch()
        
        self.recently_count = QLabel("0 songs")
        self.recently_count.setStyleSheet(f"""
            color: {self.colors['text_secondary']};
            font-size: 14px;
        """)
        header_layout.addWidget(self.recently_count)
        
        layout.addWidget(header)
        
        self.recently_scroll = QScrollArea()
        self.recently_scroll.setWidgetResizable(True)
        self.recently_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        self.recently_container = QWidget()
        self.recently_container.setObjectName("songs_container")
        
        self.recently_grid = QGridLayout(self.recently_container)
        self.recently_grid.setSpacing(16)
        self.recently_grid.setContentsMargins(0, 0, 0, 16)
        self.recently_grid.setAlignment(Qt.AlignTop)
        
        self.recently_scroll.setWidget(self.recently_container)
        layout.addWidget(self.recently_scroll, 1)
        
        return tab
    
    def create_artists_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        
        placeholder = QLabel("Artists View")
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setStyleSheet(f"""
            color: {self.colors['text_secondary']};
            font-size: 16px;
        """)
        layout.addWidget(placeholder)
        
        return tab
    
    def create_albums_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        
        placeholder = QLabel("Albums View")
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setStyleSheet(f"""
            color: {self.colors['text_secondary']};
            font-size: 16px;
        """)
        layout.addWidget(placeholder)
        
        return tab
    
    def create_discover_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(24)
        
        discover_label = QLabel("Discover New Music")
        discover_label.setStyleSheet(f"""
            color: {self.colors['text_primary']};
            font-size: 28px;
            font-weight: 800;
            margin-bottom: 8px;
        """)
        layout.addWidget(discover_label)
        
        url_section = QWidget()
        url_layout = QVBoxLayout(url_section)
        url_layout.setSpacing(12)
        
        url_label = QLabel("Search YouTube or paste playlist links")
        url_label.setStyleSheet(f"""
            color: {self.colors['text_secondary']};
            font-size: 14px;
        """)
        url_layout.addWidget(url_label)
        
        url_input_layout = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Enter YouTube URL or search query...")
        self.url_input.setMinimumHeight(44)
        self.url_input.returnPressed.connect(self.on_search)
        url_input_layout.addWidget(self.url_input, 1)
        
        search_btn = QPushButton("Search")
        search_btn.setObjectName("primary_btn")
        search_btn.clicked.connect(self.on_search)
        search_btn.setFixedWidth(100)
        url_input_layout.addWidget(search_btn)
        
        url_layout.addLayout(url_input_layout)
        layout.addWidget(url_section)
        
        results_header = QWidget()
        results_layout = QHBoxLayout(results_header)
        
        results_label = QLabel("Results")
        results_label.setStyleSheet(f"""
            color: {self.colors['text_primary']};
            font-size: 18px;
            font-weight: 700;
        """)
        results_layout.addWidget(results_label)
        results_layout.addStretch()
        
        self.preview_count = QLabel("0 songs")
        self.preview_count.setStyleSheet(f"""
            color: {self.colors['text_secondary']};
            font-size: 14px;
        """)
        results_layout.addWidget(self.preview_count)
        
        layout.addWidget(results_header)
        
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        self.song_grid_container = QWidget()
        self.song_grid_container.setObjectName("song_grid_container")
        
        self.preview_grid = QGridLayout(self.song_grid_container)
        self.preview_grid.setSpacing(16)
        self.preview_grid.setContentsMargins(0, 0, 0, 16)
        
        self.preview_scroll.setWidget(self.song_grid_container)
        layout.addWidget(self.preview_scroll, 1)
        
        action_bar = QHBoxLayout()
        action_bar.setSpacing(12)
        
        self.btn_download_sel = QPushButton("⬇ Download Selected (0)")
        self.btn_download_sel.setObjectName("secondary_btn")
        self.btn_download_sel.clicked.connect(self.download_selected)
        
        self.btn_download_all = QPushButton("⬇ Download All")
        self.btn_download_all.setObjectName("primary_btn")
        self.btn_download_all.clicked.connect(self.download_all)
        
        action_bar.addWidget(self.btn_download_sel)
        action_bar.addWidget(self.btn_download_all)
        action_bar.addStretch()
        
        layout.addLayout(action_bar)
        
        return page
    
    def create_user_menu(self):
        menu = QMenu()
        
        menu.addAction("👤 Profile", self.show_profile)
        menu.addSeparator()
        menu.addAction("⚙️ Settings", self.open_settings)
        menu.addAction("📊 Stats", self.show_stats)
        menu.addSeparator()
        menu.addAction("🚪 Log Out", self.logout)
        
        return menu
    
    def switch_page(self, page_name, button):
        for i in range(self.sidebar_layout.count()):
            widget = self.sidebar_layout.itemAt(i).widget()
            if widget and hasattr(widget, 'setStyleSheet'):
                widget.setStyleSheet(f"""
                    QPushButton {{
                        background-color: transparent;
                        color: {self.colors['text_secondary']};
                    }}
                    QPushButton:hover {{
                        color: {self.colors['text_primary']};
                        background-color: {self.colors['bg_hover']};
                    }}
                """)
        
        button.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.colors['bg_lighter']};
                color: {self.colors['text_primary']};
            }}
            QPushButton:hover {{
                background-color: {self.colors['bg_lighter']};
            }}
        """)
        
        page_map = {
            "search": 0,
            "library": 1,
            "discover": 2
        }
        
        if page_name in page_map:
            self.stacked_widget.setCurrentIndex(page_map[page_name])
            
            if page_name == "library":
                self.load_library()
            elif page_name == "search":
                # Set focus to search input when switching to search page
                self.search_input.setFocus()
    
    def load_recently_added(self):
        download_path = config.get_download_path()
        
        self.clear_grid_layout(self.recently_grid)
        
        if not os.path.exists(download_path):
            self.recently_count.setText("0 songs")
            return
        
        try:
            all_songs = []

            for root, dirs, files in os.walk(download_path):
                for file in files:
                    if file.lower().endswith(('.mp3', '.mp4', '.m4a')):
                        file_path = os.path.join(root, file)
                        mtime = os.path.getmtime(file_path)
                        all_songs.append((file_path, mtime))
            
            all_songs.sort(key=lambda x: x[1], reverse=True)
            
            recent_songs = all_songs[:20]
            
            song_cards = []
            for file_path, _ in recent_songs:
                try:
                    metadata = get_audio_metadata(file_path)
                    song_entry = {
                        'title': metadata.get('title', os.path.basename(file_path).replace('.mp3', '')),
                        'artist': metadata.get('artist', 'Unknown Artist'),
                        'file_path': file_path,
                        'metadata': metadata
                    }
                    
                    card = SongCard(song_entry)
                    card.setCursor(Qt.PointingHandCursor)
                    
                    card.file_path = file_path
                    card.metadata = metadata
                    
                    def make_click_handler(path, meta):
                        def handler(event):
                            if event.button() == Qt.LeftButton:
                                self.play_song(path, meta)
                                event.accept()
                        return handler
                    
                    card.mousePressEvent = make_click_handler(file_path, metadata)
                    
                    card.play_btn.clicked.connect(
                        lambda checked, p=file_path, m=metadata: self.play_song(p, m)
                    )
                    
                    song_cards.append(card)
                except Exception as e:
                    continue
            
            self.update_songs_grid_layout(self.recently_grid, song_cards)
            
            self.recently_song_cards = song_cards
            
            self.recently_count.setText(f"{len(song_cards)} songs")
            
        except Exception as e:
            self.recently_count.setText("0 songs")
    
    def switch_library_tab(self, tab_name):
        for btn in self.tab_buttons.values():
            btn.setChecked(False)
        
        if tab_name in self.tab_buttons:
            self.tab_buttons[tab_name].setChecked(True)
        
        tab_map = {
            "Playlists": 0,
            "Recently Added": 1,
            "Artists": 2,
            "Albums": 3
        }
        
        if tab_name in tab_map:
            self.current_library_tab = tab_name
            self.library_content.setCurrentIndex(tab_map[tab_name])
            
            if tab_name == "Playlists":
                self.load_playlists_grid()
            elif tab_name == "Recently Added":
                self.load_recently_added()
    
    def load_recent_songs(self):
        download_path = config.get_download_path()
        all_songs = []
        
        for root, dirs, files in os.walk(download_path):
            for file in files:
                if file.lower().endswith(('.mp3', '.mp4', '.m4a')):
                    file_path = os.path.join(root, file)
                    try:
                        metadata = get_audio_metadata(file_path)
                        all_songs.append({
                            'path': file_path,
                            'metadata': metadata,
                            'mtime': os.path.getmtime(file_path)
                        })
                    except:
                        continue
        
        all_songs.sort(key=lambda x: x['mtime'], reverse=True)
        
        self.recent_songs = all_songs[:20]
        
        self.recent_songs_list.clear()
        
        for song in self.recent_songs:
            metadata = song['metadata']
            title = metadata.get('title', os.path.basename(song['path']))
            artist = metadata.get('artist', 'Unknown Artist')
            
            item = QListWidgetItem(f"{title} - {artist}")
            item.setData(Qt.UserRole, song['path'])
            self.recent_songs_list.addItem(item)
    
    def load_library(self):
        if self.current_library_tab == "Playlists":
            self.load_playlists_grid()
        elif self.current_library_tab == "Recently Added":
            self.load_recently_added()
    
    def load_playlists_grid(self):
        download_path = config.get_download_path()
        
        self.clear_grid_layout(self.playlists_grid)
        self.playlist_cards = []
        
        if not os.path.exists(download_path):
            self.playlist_count.setText("0 playlists")
            self.show_empty_playlists_state()
            return
        
        try:
            # Get all playlists using PlaylistManager
            playlists = PlaylistManager.get_all_playlists(download_path)
            
            for playlist_data in playlists:
                folder_path = playlist_data["folder_path"]
                folder_name = playlist_data["name"]
                
                new_card = PlaylistCard(folder_path)
                new_card.setCursor(Qt.PointingHandCursor)
                
                new_card.delete_requested.connect(self.delete_playlist)
                new_card.play_requested.connect(self.play_playlist)
                
                new_card.mousePressEvent = lambda e, p=folder_path: self.show_playlist_songs(p)
                
                wrapper = QWidget()
                wrapper.setObjectName("playlist-card-wrapper")
                wrapper.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
                wrapper.setMinimumWidth(200)
                wrapper.setMaximumWidth(200 + 50)
                
                wrapper_layout = QHBoxLayout(wrapper)
                wrapper_layout.setContentsMargins(0, 0, 0, 0)
                wrapper_layout.addWidget(new_card)
                
                self.playlists_grid.addWidget(wrapper)
                self.playlist_cards.append(new_card)
            
            self.update_playlists_grid_layout()
            
            self.playlist_count.setText(f"{len(playlists)} playlists")
            
        except Exception as e:
            print(f"Error loading playlists: {e}")
            self.playlist_count.setText("0 playlists")
            self.show_empty_playlists_state()
    
    def show_empty_playlists_state(self):
        empty_widget = QWidget()
        layout = QVBoxLayout(empty_widget)
        layout.setAlignment(Qt.AlignCenter)
        
        empty_label = QLabel("No playlists yet")
        empty_label.setStyleSheet(f"""
            color: {self.colors['text_secondary']};
            font-size: 16px;
            margin-bottom: 16px;
        """)
        layout.addWidget(empty_label)
        
        create_btn = QPushButton("Create Your First Playlist")
        create_btn.setObjectName("primary_btn")
        create_btn.clicked.connect(self.create_new_playlist)
        create_btn.setFixedWidth(200)
        layout.addWidget(create_btn)
        
        self.playlists_grid.addWidget(empty_widget, 0, 0, Qt.AlignCenter)
    
    def update_playlists_grid_layout(self):
        self.clear_grid_layout(self.playlists_grid)
        
        container_width = self.playlists_container.width()
        
        if container_width <= 0:
            container_width = 800
        
        min_card_width = 200
        spacing = self.playlists_grid.spacing()
        max_columns = max(1, container_width // (min_card_width + spacing))
        
        row = 0
        col = 0
        
        for card in self.playlist_cards:
            wrapper = QWidget()
            wrapper.setObjectName("playlist-card-wrapper")
            wrapper.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            wrapper.setMinimumWidth(min_card_width)
            wrapper.setMaximumWidth(min_card_width + 50)
            
            wrapper_layout = QHBoxLayout(wrapper)
            wrapper_layout.setContentsMargins(0, 0, 0, 0)
            wrapper_layout.addWidget(card)
            
            self.playlists_grid.addWidget(wrapper, row, col, Qt.AlignTop)
            
            col += 1
            if col >= max_columns:
                col = 0
                row += 1
        
        self.playlists_grid.setRowStretch(row + 1, 1)
    
    def update_songs_grid_layout(self, grid_layout, song_cards):
        if not song_cards:
            return
        
        self.clear_grid_layout(grid_layout)
        
        container = grid_layout.parent()
        container_width = container.width() if container and container.width() > 0 else 800
        
        min_card_width = 180
        spacing = grid_layout.spacing()
        max_columns = max(1, container_width // (min_card_width + spacing))
        
        row = 0
        col = 0
        
        for card in song_cards:
            wrapper = QWidget()
            wrapper.setObjectName("song-card-wrapper")
            wrapper.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            
            wrapper_layout = QHBoxLayout(wrapper)
            wrapper_layout.setContentsMargins(0, 0, 0, 0)
            wrapper_layout.addWidget(card)
            
            grid_layout.addWidget(wrapper, row, col, Qt.AlignTop)
            
            col += 1
            if col >= max_columns:
                col = 0
                row += 1
        
        grid_layout.setRowStretch(row + 1, 1)
    
    def clear_grid_layout(self, grid_layout):
        for i in range(grid_layout.count()):
            item = grid_layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                for child in widget.findChildren(QWidget):
                    if isinstance(child, SongCard):
                        try:
                            child.cleanup()
                        except:
                            pass
                
                widget.setParent(None)
        
        while grid_layout.count():
            item = grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
    
    def filter_playlists(self, text):
        search_text = text.lower().strip()
        
        for card in self.playlist_cards:
            if hasattr(card, 'folder_name'):
                playlist_name = card.folder_name.lower()
                if search_text in playlist_name or not search_text:
                    card.show()
                else:
                    card.hide()

    def load_playlist_songs(self, folder_path):
        """Load playlist songs from JSON"""
        if not hasattr(self, 'playlist_songs_grid'):
            return
        
        self.clear_grid_layout(self.playlist_songs_grid)
        
        if not os.path.exists(folder_path):
            self.playlist_song_count.setText("Folder not found")
            return
        
        # Read playlist data
        playlist_data = PlaylistManager.get_playlist_info(folder_path)
        songs = playlist_data.get("songs", [])
        
        if not songs:
            empty_widget = QWidget()
            empty_layout = QVBoxLayout(empty_widget)
            empty_layout.setAlignment(Qt.AlignCenter)
            
            empty_label = QLabel("No songs in this playlist")
            empty_label.setAlignment(Qt.AlignCenter)
            empty_label.setStyleSheet(f"""
                color: {self.colors['text_secondary']};
                font-size: 16px;
                margin-bottom: 16px;
            """)
            empty_layout.addWidget(empty_label)
            
            add_songs_btn = QPushButton("+ Add Songs")
            add_songs_btn.setObjectName("primary_btn")
            add_songs_btn.clicked.connect(lambda: self.add_songs_to_playlist(folder_path))
            add_songs_btn.setFixedWidth(150)
            empty_layout.addWidget(add_songs_btn)
            
            self.playlist_songs_grid.addWidget(empty_widget, 0, 0, Qt.AlignCenter)
            self.playlist_song_count.setText("0 songs")
            return
        
        song_cards = []
        for i, song_data in enumerate(songs):
            try:
                # Check if file exists
                file_path = song_data.get('file_path')
                if not file_path or not os.path.exists(file_path):
                    # Song file not found, create a placeholder
                    song_entry = {
                        'title': song_data.get('title', 'Missing Song'),
                        'artist': song_data.get('artist', 'Unknown Artist'),
                        'file_path': file_path,
                        'metadata': song_data
                    }
                else:
                    # Load metadata from file
                    metadata = get_audio_metadata(file_path)
                    song_entry = {
                        'title': metadata.get('title', song_data.get('title')),
                        'artist': metadata.get('artist', song_data.get('artist')),
                        'file_path': file_path,
                        'metadata': metadata
                    }
                
                card = SongCard(song_entry)
                card.setCursor(Qt.PointingHandCursor)
                
                card.file_path = file_path
                card.metadata = song_data
                card.playlist_path = folder_path
                
                def make_click_handler(path, meta, exists=os.path.exists(file_path) if file_path else False):
                    def handler(event):
                        if event.button() == Qt.LeftButton and exists:
                            self.play_song(path, meta)
                            event.accept()
                        elif event.button() == Qt.LeftButton and not exists:
                            QMessageBox.warning(self, "File Not Found", 
                                              "The song file could not be found.")
                    return handler
                
                card.mousePressEvent = make_click_handler(file_path, song_data)
                
                if file_path and os.path.exists(file_path):
                    card.play_btn.clicked.connect(
                        lambda checked, p=file_path, m=song_data: self.play_song(p, m)
                    )
                else:
                    card.play_btn.setEnabled(False)
                    card.play_btn.setToolTip("File not found")
                
                # Add context menu for playlist songs
                card.setContextMenuPolicy(Qt.CustomContextMenu)
                card.customContextMenuRequested.connect(
                    lambda pos, c=card, idx=i, fp=folder_path: self.show_playlist_song_context_menu(pos, c, idx, fp)
                )
                
                song_cards.append(card)
                
            except Exception as e:
                print(f"Error loading song from playlist: {e}")
                continue
        
        if song_cards:
            container_width = self.playlist_songs_container.width()
            if container_width <= 0:
                container_width = 800
            
            min_card_width = 180
            spacing = self.playlist_songs_grid.spacing()
            max_columns = max(1, container_width // (min_card_width + spacing))
            
            row = 0
            col = 0
            
            for card in song_cards:
                wrapper = QWidget()
                wrapper.setObjectName("song-card-wrapper")
                wrapper.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
                
                wrapper_layout = QHBoxLayout(wrapper)
                wrapper_layout.setContentsMargins(0, 0, 0, 0)
                wrapper_layout.addWidget(card)
                
                self.playlist_songs_grid.addWidget(wrapper, row, col, Qt.AlignTop)
                
                col += 1
                if col >= max_columns:
                    col = 0
                    row += 1
            
            self.playlist_songs_grid.setRowStretch(row + 1, 1)
            
            self.playlist_song_cards = song_cards
            
            count = len(song_cards)
            self.playlist_song_count.setText(f"{count} song{'s' if count != 1 else ''}")
        else:
            empty_widget = QWidget()
            empty_layout = QVBoxLayout(empty_widget)
            empty_layout.setAlignment(Qt.AlignCenter)
            
            empty_label = QLabel("No accessible songs in this playlist")
            empty_label.setAlignment(Qt.AlignCenter)
            empty_label.setStyleSheet(f"""
                color: {self.colors['text_secondary']};
                font-size: 16px;
                margin-bottom: 16px;
            """)
            empty_layout.addWidget(empty_label)
            
            self.playlist_songs_grid.addWidget(empty_widget, 0, 0, Qt.AlignCenter)
            
            self.playlist_song_count.setText("0 songs")
    
    def show_playlist_songs(self, folder_path):
        """Show playlist view with JSON-based songs"""
        self.create_playlist_view_page(folder_path)
        
        if not self.playlist_view_page:
            return
        
        # Check if page already exists in stack
        for i in range(self.stacked_widget.count()):
            if self.stacked_widget.widget(i) == self.playlist_view_page:
                self.stacked_widget.setCurrentIndex(i)
                return
        
        # Add new page to stack
        index = self.stacked_widget.addWidget(self.playlist_view_page)
        self.stacked_widget.setCurrentIndex(index)
        
        # Update window title
        playlist_name = os.path.basename(folder_path)
        self.setWindowTitle(f"🎵 MusicFlow - {playlist_name}")
    
    def create_playlist_view_page(self, folder_path):
        """Create playlist view page with JSON management"""
        # Clean up existing page
        if self.playlist_view_page:
            try:
                if hasattr(self, 'playlist_song_cards'):
                    for card in self.playlist_song_cards:
                        try:
                            card.cleanup()
                        except:
                            pass
                    self.playlist_song_cards = []
                
                self.stacked_widget.removeWidget(self.playlist_view_page)
                self.playlist_view_page.deleteLater()
            except:
                pass
        
        self.playlist_view_page = QWidget()
        playlist_layout = QVBoxLayout(self.playlist_view_page)
        playlist_layout.setContentsMargins(24, 24, 24, 24)
        playlist_layout.setSpacing(16)
        
        # Back button
        back_btn = QPushButton("← Back to Library")
        back_btn.setObjectName("secondary_btn")
        back_btn.clicked.connect(self.back_to_library)
        back_btn.setFixedWidth(150)
        playlist_layout.addWidget(back_btn)
        
        # Playlist header
        playlist_data = PlaylistManager.get_playlist_info(folder_path)
        playlist_name = playlist_data.get("name", os.path.basename(folder_path))
        
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(16)
        
        # Playlist info
        info_layout = QVBoxLayout()
        info_layout.setSpacing(8)
        
        playlist_title = QLabel(f"🎵 {playlist_name}")
        playlist_title.setStyleSheet(f"""
            color: {self.colors['text_primary']};
            font-size: 28px;
            font-weight: 800;
        """)
        info_layout.addWidget(playlist_title)
        
        # Description if available
        description = playlist_data.get("metadata", {}).get("description", "")
        if description:
            desc_label = QLabel(description)
            desc_label.setStyleSheet(f"""
                color: {self.colors['text_secondary']};
                font-size: 14px;
                font-style: italic;
                margin-top: 4px;
            """)
            desc_label.setWordWrap(True)
            info_layout.addWidget(desc_label)
        
        header_layout.addLayout(info_layout, 1)
        
        # Action buttons
        action_layout = QHBoxLayout()
        action_layout.setSpacing(8)
        
        play_all_btn = QPushButton("▶ Play All (Random)")
        play_all_btn.setObjectName("primary_btn")
        play_all_btn.setFixedWidth(150)
        play_all_btn.clicked.connect(lambda: self.play_playlist_random(folder_path))
        action_layout.addWidget(play_all_btn)
        
        add_songs_btn = QPushButton("+ Add Songs")
        add_songs_btn.setObjectName("secondary_btn")
        add_songs_btn.setFixedWidth(120)
        add_songs_btn.clicked.connect(lambda: self.add_songs_to_playlist(folder_path))
        action_layout.addWidget(add_songs_btn)
        
        fix_metadata_btn = QPushButton("🛠 Fix Metadata")
        fix_metadata_btn.setObjectName("secondary_btn")
        fix_metadata_btn.setFixedWidth(120)
        fix_metadata_btn.clicked.connect(lambda: self.fix_playlist_metadata(folder_path))
        action_layout.addWidget(fix_metadata_btn)
        
        header_layout.addLayout(action_layout)
        
        playlist_layout.addWidget(header_widget)
        
        # Song count
        self.playlist_song_count = QLabel("Loading songs...")
        self.playlist_song_count.setStyleSheet(f"""
            color: {self.colors['text_secondary']};
            font-size: 14px;
            margin-bottom: 16px;
        """)
        playlist_layout.addWidget(self.playlist_song_count)
        
        # Songs grid
        self.playlist_songs_scroll = QScrollArea()
        self.playlist_songs_scroll.setWidgetResizable(True)
        self.playlist_songs_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.playlist_songs_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        self.playlist_songs_container = QWidget()
        self.playlist_songs_container.setObjectName("songs_container")
        
        self.playlist_songs_grid = QGridLayout(self.playlist_songs_container)
        self.playlist_songs_grid.setSpacing(16)
        self.playlist_songs_grid.setContentsMargins(0, 0, 0, 16)
        self.playlist_songs_grid.setAlignment(Qt.AlignTop)
        
        self.playlist_songs_scroll.setWidget(self.playlist_songs_container)
        playlist_layout.addWidget(self.playlist_songs_scroll, 1)
        
        # Load songs after a short delay
        QTimer.singleShot(100, lambda: self.load_playlist_songs(folder_path))
        
        return self.playlist_view_page

    def show_playlist_song_context_menu(self, position, song_card, song_index, playlist_path):
        """Show context menu for playlist song"""
        from PyQt5.QtWidgets import QMenu, QAction
        
        menu = QMenu(self)
        
        # Play action
        play_action = QAction("▶ Play", self)
        play_action.triggered.connect(lambda: self.play_song(song_card.file_path, song_card.metadata))
        menu.addAction(play_action)
        
        menu.addSeparator()
        
        # Remove from playlist
        remove_action = QAction("➖ Remove from Playlist", self)
        remove_action.triggered.connect(lambda: self.remove_song_from_playlist(playlist_path, song_index))
        menu.addAction(remove_action)
        
        # Fix metadata
        fix_action = QAction("🛠 Fix Metadata", self)
        fix_action.triggered.connect(lambda: self.fix_song_metadata(playlist_path, song_index))
        menu.addAction(fix_action)
        
        menu.exec_(song_card.mapToGlobal(position))
    
    def fix_song_metadata(self, playlist_path, song_index):
        """Fix metadata for a single song in playlist"""
        playlist_data = PlaylistManager.get_playlist_info(playlist_path)
        
        if 0 <= song_index < len(playlist_data["songs"]):
            song = playlist_data["songs"][song_index]
            file_path = song.get("file_path")
            
            if file_path and os.path.exists(file_path):
                try:
                    metadata = get_audio_metadata(file_path)
                    
                    # Update metadata
                    PlaylistManager.update_song_metadata(playlist_path, song_index, {
                        "title": metadata.get("title", song.get("title")),
                        "artist": metadata.get("artist", song.get("artist")),
                        "album": metadata.get("album", song.get("album")),
                        "duration": metadata.get("duration", song.get("duration")),
                        "has_cover": metadata.get("has_cover", song.get("has_cover", False)),
                        "cover_mime": metadata.get("cover_mime", song.get("cover_mime")),
                        "cover_size": metadata.get("cover_size", song.get("cover_size", 0)),
                        "needs_fix": metadata.get("needs_fix", False)
                    })
                    
                    QMessageBox.information(self, "Metadata Fixed", 
                                          f"Metadata for '{song.get('title')}' has been updated.")
                    
                    # Reload playlist
                    self.load_playlist_songs(playlist_path)
                    
                except Exception as e:
                    QMessageBox.warning(self, "Error", 
                                      f"Could not fix metadata: {e}")
            else:
                QMessageBox.warning(self, "File Not Found", 
                                  "The song file could not be found.")
    
    def fix_playlist_metadata(self, folder_path):
        """Fix metadata for all songs in playlist"""
        result = PlaylistManager.fix_playlist_metadata(folder_path)
        
        if result["fixed"] > 0:
            QMessageBox.information(self, "Metadata Fixed", 
                                  f"Fixed metadata for {result['fixed']} songs.\n"
                                  f"Errors: {result['errors']}")
            
            # Reload playlist
            self.load_playlist_songs(folder_path)
        else:
            QMessageBox.information(self, "No Changes", 
                                  "No metadata needed fixing.")
    
    def remove_song_from_playlist(self, playlist_path, song_index):
        """Remove song from playlist JSON"""
        reply = QMessageBox.question(
            self, "Remove Song",
            "Are you sure you want to remove this song from the playlist?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            if PlaylistManager.remove_song_from_playlist(playlist_path, song_index):
                QMessageBox.information(self, "Song Removed", 
                                      "Song has been removed from the playlist.")
                
                # Reload playlist
                self.load_playlist_songs(playlist_path)
            else:
                QMessageBox.warning(self, "Error", 
                                  "Could not remove song from playlist.")

    def back_to_library(self):
        self.setWindowTitle("🎵 MusicFlow - Smart Music Player")
        
        self.stacked_widget.setCurrentIndex(1)
        
        self.load_library()

    def play_playlist(self, folder_path):
        """Play all songs in playlist from JSON references (random order)"""
        playlist_data = PlaylistManager.get_playlist_info(folder_path)
        songs = playlist_data.get("songs", [])
        
        if not songs:
            QMessageBox.warning(self, "Empty Playlist", "No songs in this playlist.")
            return
        
        # Filter songs that actually exist
        valid_songs = []
        for song in songs:
            file_path = song.get("file_path")
            if file_path and os.path.exists(file_path):
                valid_songs.append((file_path, song))
        
        if not valid_songs:
            QMessageBox.warning(self, "No Accessible Songs", 
                              "Could not access any songs in this playlist.")
            return
        
        self.audio_player.clear_playlist()
        
        for file_path, song_data in valid_songs:
            self.audio_player.add_to_playlist(file_path, song_data)
        
        if valid_songs:
            self.audio_player.set_current_playlist(valid_songs)
            # Enable shuffle mode for random playback
            self.audio_player.shuffle_mode = True
            self.audio_player.update_shuffle_button_style()
            # Pick a random song to start with
            file_path, metadata = random.choice(valid_songs)
            self.audio_player.play_song(file_path, metadata)
    
    def play_playlist_random(self, folder_path):
        """Play all songs in playlist in random order"""
        self.play_playlist(folder_path)
    
    def play_song(self, path, meta=None):
        success = self.audio_player.play_song(path, meta)
        
        # Update sidebar with currently playing song
        if success and meta:
            title = meta.get("title", os.path.basename(path))
            artist = meta.get("artist", "Unknown Artist")
            self.sidebar_song_title.setText(title)
            self.sidebar_song_artist.setText(artist)
        
        return success
    
    def on_playback_state_changed(self, is_playing):
        pass
    
    def on_search(self):
        text = self.url_input.text().strip()
        if not text:
            return

        if self.current_preview_thread:
            self.current_preview_thread.stop()
            self.current_preview_thread = None

        for card in self.preview_cards:
            if card:
                card.cleanup()
                card.deleteLater()
        
        self.preview_cards.clear()
        self.all_preview_songs.clear()

        self.current_preview_thread = PreviewThread(text)
        self.current_preview_thread.finished.connect(self.show_preview)
        self.current_preview_thread.error.connect(lambda e: print(f"Search error: {e}"))
        self.current_preview_thread.start()
    
    def on_search_text_changed(self, text):
        """Handle search text changes with debouncing"""
        if len(text.strip()) >= 2:  # Minimum search length
            self.search_timer.stop()
            self.search_timer.start(500)  # 500ms debounce
        elif len(text.strip()) == 0:
            # Clear search if empty
            self.clear_search_results()
    
    def on_search_enter(self):
        """Handle search on Enter key"""
        text = self.search_input.text().strip()
        if text:
            self.perform_search()
            self.switch_page("search", self.btn_search)
    
    def perform_search(self):
        """Perform search and update results"""
        query = self.search_input.text().strip()
        
        if not query:
            return
        
        # Clear previous results
        self.clear_search_results()
        
        # Update search label
        self.search_label.setText(f"Search Results for '{query}'")
        
        # Perform search using PlaylistManager
        download_path = config.get_download_path()
        search_results = PlaylistManager.search_in_playlists(download_path, query)
        
        # Update search results
        self.search_results = search_results
        
        # Generate recommendations
        recommendations = PlaylistManager.generate_recommendations(download_path)
        self.search_results["recommendations"] = recommendations
        
        # Display results
        self.display_search_results()
        
        # Update count
        total_results = len(search_results["songs"]) + len(search_results["playlists"])
        self.search_count.setText(f"{total_results} results found")
    
    def clear_search_results(self):
        """Clear all search results"""
        self.clear_grid_layout(self.search_songs_grid)
        self.clear_grid_layout(self.search_playlists_grid)
        self.clear_grid_layout(self.recommendations_grid)
        
        self.search_label.setText("Search Music")
        self.search_count.setText("")
    
    def display_search_results(self):
        """Display search results in tabs"""
        
        # Display songs
        if self.search_results["songs"]:
            song_cards = []
            for song_result in self.search_results["songs"][:50]:  # Limit to 50 results
                try:
                    # Create song entry
                    song_entry = {
                        'title': song_result.get("title", "Unknown"),
                        'artist': song_result.get("artist", "Unknown Artist"),
                        'file_path': song_result.get("file_path"),
                        'metadata': {
                            'title': song_result.get("title"),
                            'artist': song_result.get("artist"),
                            'album': song_result.get("album")
                        }
                    }
                    
                    card = SongCard(song_entry)
                    card.setCursor(Qt.PointingHandCursor)
                    card.file_path = song_result.get("file_path")
                    card.metadata = song_result
                    
                    # Add click handler
                    def make_click_handler(path, meta):
                        def handler(event):
                            if event.button() == Qt.LeftButton and path and os.path.exists(path):
                                self.play_song(path, meta)
                            elif event.button() == Qt.LeftButton and (not path or not os.path.exists(path)):
                                QMessageBox.warning(self, "File Not Found", 
                                                  "The song file could not be found.")
                        return handler
                    
                    card.mousePressEvent = make_click_handler(song_result.get("file_path"), song_result)
                    
                    if song_result.get("file_path") and os.path.exists(song_result.get("file_path")):
                        card.play_btn.clicked.connect(
                            lambda checked, p=song_result.get("file_path"), m=song_result: 
                            self.play_song(p, m) if p and os.path.exists(p) else None
                        )
                    else:
                        card.play_btn.setEnabled(False)
                        card.play_btn.setToolTip("File not found")
                    
                    # Add context menu
                    card.setContextMenuPolicy(Qt.CustomContextMenu)
                    card.customContextMenuRequested.connect(
                        lambda pos, s=song_result: self.show_search_song_context_menu(pos, s)
                    )
                    
                    song_cards.append(card)
                except Exception as e:
                    print(f"Error creating search result card: {e}")
                    continue
            
            # Update songs grid
            container_width = self.search_songs_container.width()
            if container_width <= 0:
                container_width = 800
            
            min_card_width = 180
            spacing = self.search_songs_grid.spacing()
            max_columns = max(1, container_width // (min_card_width + spacing))
            
            row = 0
            col = 0
            
            for card in song_cards:
                wrapper = QWidget()
                wrapper.setObjectName("song-card-wrapper")
                wrapper.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
                
                wrapper_layout = QHBoxLayout(wrapper)
                wrapper_layout.setContentsMargins(0, 0, 0, 0)
                wrapper_layout.addWidget(card)
                
                self.search_songs_grid.addWidget(wrapper, row, col, Qt.AlignTop)
                
                col += 1
                if col >= max_columns:
                    col = 0
                    row += 1
            
            self.search_songs_grid.setRowStretch(row + 1, 1)
        else:
            # Show empty state for songs
            empty_label = QLabel("No songs found")
            empty_label.setAlignment(Qt.AlignCenter)
            empty_label.setStyleSheet(f"""
                color: {self.colors['text_secondary']};
                font-size: 16px;
                padding: 40px;
            """)
            self.search_songs_grid.addWidget(empty_label, 0, 0, Qt.AlignCenter)
        
        # Display playlists
        if self.search_results["playlists"]:
            for playlist_result in self.search_results["playlists"][:20]:  # Limit to 20 results
                folder_path = playlist_result.get("folder_path")
                if folder_path and os.path.exists(folder_path):
                    card = PlaylistCard(folder_path)
                    card.setCursor(Qt.PointingHandCursor)
                    card.delete_requested.connect(self.delete_playlist)
                    card.play_requested.connect(self.play_playlist)
                    card.mousePressEvent = lambda e, p=folder_path: self.show_playlist_songs(p)
                    
                    wrapper = QWidget()
                    wrapper.setObjectName("playlist-card-wrapper")
                    wrapper.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
                    
                    wrapper_layout = QHBoxLayout(wrapper)
                    wrapper_layout.setContentsMargins(0, 0, 0, 0)
                    wrapper_layout.addWidget(card)
                    
                    self.search_playlists_grid.addWidget(wrapper)
        else:
            # Show empty state for playlists
            empty_label = QLabel("No playlists found")
            empty_label.setAlignment(Qt.AlignCenter)
            empty_label.setStyleSheet(f"""
                color: {self.colors['text_secondary']};
                font-size: 16px;
                padding: 40px;
            """)
            self.search_playlists_grid.addWidget(empty_label, 0, 0, Qt.AlignCenter)
        
        # Display recommendations
        if self.search_results["recommendations"]:
            for rec in self.search_results["recommendations"][:4]:  # Show top 4 recommendations
                playlist = rec.get("playlist", {})
                folder_path = playlist.get("folder_path")
                
                if folder_path and os.path.exists(folder_path):
                    card = PlaylistCard(folder_path)
                    card.setCursor(Qt.PointingHandCursor)
                    card.delete_requested.connect(self.delete_playlist)
                    card.play_requested.connect(self.play_playlist)
                    card.mousePressEvent = lambda e, p=folder_path: self.show_playlist_songs(p)
                    
                    # Add recommendation badge
                    reason = rec.get("reason", "Recommended")
                    card.setToolTip(f"{reason} - Score: {rec.get('score', 0):.1f}")
                    
                    wrapper = QWidget()
                    wrapper.setObjectName("playlist-card-wrapper")
                    wrapper.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
                    
                    wrapper_layout = QVBoxLayout(wrapper)
                    wrapper_layout.setContentsMargins(0, 0, 0, 0)
                    
                    # Recommendation label
                    rec_label = QLabel(f"⭐ {reason}")
                    rec_label.setStyleSheet(f"""
                        color: {self.colors['accent_green']};
                        font-size: 11px;
                        font-weight: 600;
                        margin-bottom: 4px;
                    """)
                    rec_label.setAlignment(Qt.AlignCenter)
                    wrapper_layout.addWidget(rec_label)
                    
                    wrapper_layout.addWidget(card)
                    
                    self.recommendations_grid.addWidget(wrapper)
        else:
            # Show empty state for recommendations
            empty_label = QLabel("No recommendations available")
            empty_label.setAlignment(Qt.AlignCenter)
            empty_label.setStyleSheet(f"""
                color: {self.colors['text_secondary']};
                font-size: 16px;
                padding: 40px;
            """)
            self.recommendations_grid.addWidget(empty_label, 0, 0, Qt.AlignCenter)
    
    def show_search_song_context_menu(self, position, song_result):
        """Show context menu for search result song"""
        from PyQt5.QtWidgets import QMenu, QAction
        
        menu = QMenu(self)
        
        # Play action
        file_path = song_result.get("file_path")
        if file_path and os.path.exists(file_path):
            play_action = QAction("▶ Play", self)
            play_action.triggered.connect(lambda: self.play_song(file_path, song_result))
            menu.addAction(play_action)
        
        menu.addSeparator()
        
        # Add to playlist action
        add_to_playlist_action = QAction("+ Add to Playlist", self)
        add_to_playlist_action.triggered.connect(lambda: self.add_song_to_playlist_dialog(song_result))
        menu.addAction(add_to_playlist_action)
        
        menu.exec_(self.mapToGlobal(position))
    
    def add_song_to_playlist_dialog(self, song_result):
        """Add search result song to a playlist"""
        download_path = config.get_download_path()
        playlists = PlaylistManager.get_all_playlists(download_path)
        
        if not playlists:
            QMessageBox.information(self, "No Playlists", 
                                  "Create a playlist first to add songs.")
            return
        
        # Create dialog to select playlist
        items = [p["name"] for p in playlists]
        item, ok = QInputDialog.getItem(
            self, "Add to Playlist",
            "Select playlist:", items, 0, False
        )
        
        if ok and item:
            # Find selected playlist
            for playlist in playlists:
                if playlist["name"] == item:
                    # Add song to playlist
                    if PlaylistManager.add_song_to_playlist(
                        playlist["folder_path"], 
                        song_result.get("file_path"), 
                        song_result
                    ):
                        QMessageBox.information(self, "Song Added", 
                                              f"Added to '{item}' playlist.")
                    else:
                        QMessageBox.warning(self, "Error", 
                                          "Could not add song to playlist.")
                    break
    
    def show_preview(self, data):
        songs = data.get("songs", [])
        self.all_preview_songs = [song_to_dict(s) for s in songs]
        
        for card in self.preview_cards:
            if card:
                card.cleanup()
                card.deleteLater()
        self.preview_cards.clear()
        
        self.clear_grid_layout(self.preview_grid)
        
        for song in self.all_preview_songs:
            try:
                card = SongCard(song)
                if card:
                    card.song_data = song
                    card.mousePressEvent = lambda e, c=card: self.toggle_card(c)
                    card.play_btn.clicked.connect(lambda checked, c=card: self.on_card_play_clicked(c))
                    self.preview_cards.append(card)
            except Exception as e:
                continue
        
        self.update_preview_grid_layout()
        
        self.preview_count.setText(f"{len(self.preview_cards)} songs")
        self.update_selected_count()
    
    def update_preview_grid_layout(self):
        if not self.preview_cards:
            return
        
        self.clear_grid_layout(self.preview_grid)
        
        container_width = self.song_grid_container.width()
        if container_width <= 0:
            container_width = 800
        
        min_card_width = 180
        spacing = self.preview_grid.spacing()
        max_columns = max(1, container_width // (min_card_width + spacing))
        
        row = 0
        col = 0
        
        for card in self.preview_cards:
            if not card:
                continue
                
            wrapper = QWidget()
            wrapper.setObjectName("song-card-wrapper")
            wrapper.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            
            wrapper_layout = QHBoxLayout(wrapper)
            wrapper_layout.setContentsMargins(0, 0, 0, 0)
            wrapper_layout.addWidget(card)
            
            self.preview_grid.addWidget(wrapper, row, col, Qt.AlignTop)
            
            col += 1
            if col >= max_columns:
                col = 0
                row += 1
        
        self.preview_grid.setRowStretch(row + 1, 1)
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        
        if hasattr(self, 'playlist_cards') and self.playlist_cards and self.current_library_tab == "Playlists":
            if hasattr(self, '_resize_timer'):
                self._resize_timer.stop()
            
            self._resize_timer = QTimer()
            self._resize_timer.setSingleShot(True)
            self._resize_timer.timeout.connect(self.update_playlists_grid_layout)
            self._resize_timer.start(150)
        
        if hasattr(self, 'preview_cards') and self.preview_cards:
            QTimer.singleShot(100, self.update_preview_grid_layout)
        
        # Update search results layout
        if self.stacked_widget.currentWidget() == self.search_page:
            QTimer.singleShot(100, self.display_search_results)
    
    def on_card_play_clicked(self, card):
        if hasattr(card, 'song_data'):
            song_data = card.song_data
            title = song_data.get("title", "Unknown")
            artist = song_data.get("artist", "Unknown")
    
    def toggle_card(self, card):
        if card:
            card.set_selected(not card.selected)
            self.update_selected_count()
    
    def update_selected_count(self):
        count = sum(1 for card in self.preview_cards if card and card.selected)
        self.btn_download_sel.setText(f"⬇ Download Selected ({count})")
    
    def download_selected(self):
        selected = []
        for card in self.preview_cards:
            if card and card.selected and hasattr(card, 'song_data'):
                selected.append(card.song_data)
        self.start_download(selected)
    
    def download_all(self):
        songs = []
        for card in self.preview_cards:
            if card and hasattr(card, 'song_data'):
                songs.append(card.song_data)
        self.start_download(songs)
    
    def start_download(self, songs):
        if not songs:
            return
        
        self.progress = ProgressDialog(len(songs), self)
        self.progress.show()
        
        self.download_thread = DownloadThread(songs, config.get_download_path())
        self.download_thread.progress.connect(self.progress.update_progress)
        self.download_thread.finished.connect(self.on_download_finished)
        self.download_thread.start()
    
    def on_download_finished(self):
        if hasattr(self, 'progress'):
            self.progress.complete()
        
        QTimer.singleShot(1000, self.load_library)
        QTimer.singleShot(1500, self.load_recent_songs)
    
    def on_recent_song_clicked(self, item):
        path = item.data(Qt.UserRole)
        if os.path.exists(path):
            metadata = get_audio_metadata(path)
            self.play_song(path, metadata)
    
    def create_new_playlist(self):
        dialog = CreatePlaylistDialog(self)
        if dialog.exec_():
            # Create playlist using PlaylistManager
            playlist_name = dialog.get_playlist_name()
            playlist_folder = os.path.join(config.get_download_path(), playlist_name)
            
            if PlaylistManager.create_playlist(playlist_folder, playlist_name):
                self.load_playlists_grid()
                QMessageBox.information(self, "Playlist Created", 
                                      f"Playlist '{playlist_name}' created successfully.")
            else:
                QMessageBox.warning(self, "Error", 
                                  "Could not create playlist.")
    
    def add_songs_to_playlist(self, folder_path):
        """Add songs to playlist JSON"""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Songs to Add",
            "",
            "Audio Files (*.mp3 *.mp4 *.m4a *.flac *.wav *.ogg);;All Files (*.*)"
        )
        
        if not files:
            return
        
        added_count = 0
        for file_path in files:
            try:
                metadata = get_audio_metadata(file_path)
                if PlaylistManager.add_song_to_playlist(folder_path, file_path, metadata):
                    added_count += 1
            except Exception as e:
                print(f"Error adding song {file_path}: {e}")
        
        # Reload playlist
        self.load_playlist_songs(folder_path)
        
        QMessageBox.information(
            self, "Songs Added",
            f"Added {added_count} song reference(s) to the playlist."
        )
    
    def delete_playlist(self, folder_path):
        """Delete playlist folder and JSON"""
        playlist_name = os.path.basename(folder_path)
        
        reply = QMessageBox.question(
            self, "Delete Playlist",
            f"Are you sure you want to delete the playlist '{playlist_name}'?\n\n"
            "Note: This will only delete the playlist reference, not the song files.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                import shutil
                shutil.rmtree(folder_path)
                
                self.load_playlists_grid()
                
                QMessageBox.information(
                    self, "Playlist Deleted",
                    f"Playlist '{playlist_name}' has been deleted."
                )
            except Exception as e:
                QMessageBox.warning(
                    self, "Error",
                    f"Could not delete playlist: {e}"
                )
    
    def show_library(self):
        self.switch_page("library", self.btn_library)
    
    def show_search(self):
        self.switch_page("search", self.btn_search)
    
    def show_discover(self):
        self.switch_page("discover", self.btn_discover)
    
    def open_settings(self):
        SettingsDialog(self).exec_()
    
    def check_and_fix_metadata(self):
        # Check if user has chosen to ignore metadata fixes
        if config.get("ignore_metadata_fix", False):
            return
            
        from app.desktop.utils.metadata import get_audio_metadata
        
        download_path = config.get_download_path()
        audio_files = []
        
        for root, dirs, files in os.walk(download_path):
            for file in files:
                if file.lower().endswith(('.mp3', '.mp4', '.m4a')):
                    audio_files.append(os.path.join(root, file))
        
        bad = []
        for file_path in audio_files:
            try:
                metadata = get_audio_metadata(file_path)
                if metadata.get("needs_fix"):
                    bad.append({
                        "file_path": file_path,
                        "metadata": metadata
                    })
            except Exception as e:
                print(f"Error checking metadata for {file_path}: {e}")
        
        if bad:
            FixMetadataDialog(bad, self).exec_()
    
    def on_back(self):
        if self.stacked_widget.currentWidget() == self.playlist_view_page:
            self.back_to_library()
    
    def on_forward(self):
        pass
    
    def toggle_play(self):
        self.audio_player.toggle_play()
    
    def previous_song(self):
        self.audio_player.previous_song()
    
    def next_song(self):
        self.audio_player.next_song()
    
    def show_upgrade_dialog(self):
        pass
    
    def show_profile(self):
        pass
    
    def show_stats(self):
        pass
    
    def logout(self):
        pass
    
    def setup_tray(self):
        self.tray = QSystemTrayIcon(self)
        pix = QPixmap(64, 64)
        pix.fill(Qt.transparent)
        
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        
        p.setBrush(QColor(self.colors['accent_green']))
        p.setPen(Qt.NoPen)
        p.drawEllipse(4, 4, 56, 56)
        
        p.setPen(Qt.white)
        p.setFont(QFont("Arial", 28))
        p.drawText(pix.rect(), Qt.AlignCenter, "♪")
        p.end()
        
        self.tray.setIcon(QIcon(pix))
        
        menu = QMenu()
        menu.addAction("Show", self.show)
        menu.addAction("Exit", QApplication.quit)
        self.tray.setContextMenu(menu)
        self.tray.show()
    
    def closeEvent(self, e):
        if self.current_preview_thread:
            self.current_preview_thread.stop()
            self.current_preview_thread = None
        
        if self.download_thread:
            if self.download_thread.isRunning():
                self.download_thread.terminate()
                self.download_thread.wait()
            self.download_thread = None
        
        for card in self.preview_cards:
            if card:
                card.cleanup()
        
        for card in self.playlist_cards:
            if card:
                card.cleanup()
        
        self.audio_player.stop_playback()
        
        config.set("window_size", [self.width(), self.height()])
        e.accept()
    
    def get_spotify_stylesheet(self):
        return f"""
        QMainWindow, QWidget, QDialog {{
            background-color: {self.colors['bg_dark']};
            color: {self.colors['text_primary']};
            font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
            font-size: 13px;
            border: none;
        }}
        
        QFrame#top_bar {{
            background-color: {self.colors['bg_dark']};
            border-bottom: 1px solid {self.colors['bg_lighter']};
        }}
        
        QPushButton#nav_btn {{
            background-color: transparent;
            color: {self.colors['text_secondary']};
            border: none;
            border-radius: 50%;
            padding: 8px;
            font-size: 18px;
            min-width: 32px;
            min-height: 32px;
            max-width: 32px;
            max-height: 32px;
        }}

        #song_grid_container, #playlists_container, #songs_container {{
            background-color: transparent;
            border: none;
            padding: 0;
        }}
        #playlists_container {{
            background-color: {self.colors['bg_dark']};
            border: none;
            padding: 0;
        }}
        
        .playlist-card-wrapper {{
            background-color: transparent;
            border: none;
            padding: 8px;
        }}
        
        QPushButton#nav_btn:hover {{
            background-color: {self.colors['bg_lighter']};
            color: {self.colors['text_primary']};
        }}
        
        QPushButton#user_btn {{
            background-color: {self.colors['bg_lighter']};
            color: {self.colors['text_primary']};
            border: none;
            border-radius: 23px;
            padding: 4px 12px;
            font-weight: 600;
            font-size: 12px;
        }}
        
        QPushButton#user_btn:hover {{
            background-color: {self.colors['bg_hover']};
        }}
        
        QFrame#sidebar {{
            background-color: {self.colors['bg_dark']};
            border-right: 1px solid {self.colors['bg_lighter']};
        }}
        
        QPushButton#sidebar_btn {{
            background-color: transparent;
            color: {self.colors['text_secondary']};
            border: none;
            border-radius: 4px;
            padding: 8px 12px;
            text-align: left;
            font-size: 14px;
            font-weight: 600;
            margin: 2px 8px;
        }}
        
        QPushButton#sidebar_btn:hover {{
            color: {self.colors['text_primary']};
            background-color: {self.colors['bg_hover']};
        }}
        
        QPushButton#sidebar_btn.active {{
            background-color: {self.colors['bg_lighter']};
            color: {self.colors['text_primary']};
        }}
        
        QPushButton#sidebar_btn.active:hover {{
            background-color: {self.colors['bg_lighter']};
        }}
        
        QScrollArea {{
            background-color: transparent;
            border: none;
        }}
        
        QScrollArea > QWidget > QWidget {{
            background-color: transparent;
        }}
        
        QScrollBar:vertical {{
            background-color: {self.colors['bg_dark']};
            width: 8px;
            border-radius: 4px;
        }}
        
        QScrollBar::handle:vertical {{
            background-color: {self.colors['bg_lighter']};
            border-radius: 4px;
            min-height: 30px;
        }}
        
        QScrollBar::handle:vertical:hover {{
            background-color: {self.colors['text_disabled']};
        }}
        
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        
        #song_grid_container, #playlists_container, #songs_container {{
            background-color: transparent;
            border: none;
        }}
        
        .song-card-wrapper, .playlist-card-wrapper {{
            background-color: transparent;
            border: none;
            padding: 8px;
        }}
        
        QFrame#song_card {{
            background-color: {self.colors['bg_lighter']};
            border: 1px solid transparent;
            border-radius: 8px;
            padding: 12px;
            min-width: 180px;
            max-width: 180px;
            min-height: 240px;
            max-height: 240px;
        }}
        
        QFrame#song_card:hover {{
            background-color: {self.colors['bg_hover']};
            border: 1px solid {self.colors['text_secondary']};
        }}
        
        QFrame#playlist_card {{
            background-color: {self.colors['bg_lighter']};
            border: 1px solid transparent;
            border-radius: 8px;
            padding: 12px;
            min-width: 180px;
            min-height: 220px;
        }}
        
        QFrame#playlist_card:hover {{
            background-color: {self.colors['bg_hover']};
            border: 1px solid {self.colors['text_secondary']};
        }}
        
        QFrame#song_card QLabel, QFrame#playlist_card QLabel {{
            background-color: transparent;
        }}
        
        QFrame#song_card QPushButton, QFrame#playlist_card QPushButton {{
            background-color: {self.colors['accent_green']};
            color: #000000;
            border: none;
            border-radius: 20px;
            font-size: 18px;
            font-weight: bold;
            min-width: 40px;
            min-height: 40px;
            max-width: 40px;
            max-height: 40px;
        }}
        
        QFrame#song_card QPushButton:hover, QFrame#playlist_card QPushButton:hover {{
            background-color: {self.colors['accent_light']};
        }}
        
        QPushButton#primary_btn {{
            background-color: {self.colors['accent_green']};
            color: #000000;
            border: none;
            border-radius: 500px;
            padding: 12px 32px;
            font-weight: 500;
            font-size: 8px;
            text-transform: uppercase;
            letter-spacing: 0.8px;
        }}
        
        QPushButton#primary_btn:hover {{
            background-color: {self.colors['accent_light']};
        }}
        
        QPushButton#primary_btn:pressed {{
            background-color: {self.colors['accent_green']};
        }}
        
        QPushButton#secondary_btn {{
            background-color: transparent;
            color: {self.colors['text_primary']};
            border: 1px solid {self.colors['text_disabled']};
            border-radius: 500px;
            padding: 8px 25px;
            font-weight: 600;
            font-size: 11px;
        }}
        
        QPushButton#secondary_btn:hover {{
            border-color: {self.colors['text_primary']};
        }}
        
        QLineEdit {{
            background-color: {self.colors['bg_lighter']};
            border: 2px solid transparent;
            border-radius: 20px;
            padding: 10px 20px;
            color: {self.colors['text_primary']};
            font-size: 14px;
            selection-background-color: {self.colors['accent_green']};
            selection-color: #000000;
        }}
        
        QLineEdit:focus {{
            border: 2px solid {self.colors['text_primary']};
            background-color: {self.colors['bg_hover']};
        }}
        
        QLineEdit::placeholder {{
            color: {self.colors['text_disabled']};
        }}
        
        QFrame#player_bar {{
            background-color: {self.colors['bg_lighter']};
            border-top: 1px solid {self.colors['bg_hover']};
        }}
        
        QSlider::groove:horizontal {{
            background-color: {self.colors['text_disabled']};
            height: 4px;
            border-radius: 2px;
        }}
        
        QSlider::sub-page:horizontal {{
            background-color: {self.colors['accent_green']};
            height: 4px;
            border-radius: 2px;
        }}
        
        QSlider::handle:horizontal {{
            background-color: {self.colors['text_primary']};
            width: 12px;
            height: 12px;
            margin: -4px 0;
            border-radius: 6px;
            border: none;
        }}
        
        QSlider::handle:horizontal:hover {{
            background-color: {self.colors['accent_light']};
        }}
        
        QPushButton#player_btn {{
            background-color: transparent;
            color: {self.colors['text_primary']};
            border: none;
            border-radius: 50%;
            padding: 8px;
            font-size: 16px;
        }}
        
        QPushButton#player_btn:hover {{
            color: {self.colors['accent_green']};
        }}
        
        QPushButton#play_btn {{
            background-color: {self.colors['text_primary']};
            color: #000000;
            border: none;
            border-radius: 50%;
            padding: 8px;
            font-size: 20px;
            min-width: 32px;
            min-height: 32px;
            max-width: 32px;
            max-height: 32px;
        }}
        
        QPushButton#play_btn:hover {{
            background-color: {self.colors['accent_light']};
            color: #000000;
        }}
        
        QListWidget {{
            background-color: transparent;
            border: none;
            outline: none;
        }}
        
        QListWidget::item {{
            background-color: transparent;
            color: {self.colors['text_secondary']};
            padding: 8px 12px;
            border-radius: 4px;
            margin: 2px 4px;
        }}
        
        QListWidget::item:hover {{
            background-color: {self.colors['bg_lighter']};
        }}
        
        QListWidget::item:selected {{
            background-color: {self.colors['bg_hover']};
            color: {self.colors['text_primary']};
        }}
        
        QProgressBar {{
            background-color: {self.colors['bg_lighter']};
            border: none;
            border-radius: 2px;
            text-align: center;
            font-size: 11px;
            color: {self.colors['text_primary']};
            height: 4px;
        }}
        
        QProgressBar::chunk {{
            background-color: {self.colors['accent_green']};
            border-radius: 2px;
        }}
        
        QToolTip {{
            background-color: {self.colors['bg_light']};
            color: {self.colors['text_primary']};
            border: 1px solid {self.colors['bg_lighter']};
            border-radius: 4px;
            padding: 8px;
            font-size: 12px;
        }}
        """