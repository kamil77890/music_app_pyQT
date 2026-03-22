# playlist_card.py
import os
import json
from typing import Optional
from PyQt5.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
    QWidget, QGridLayout, QMenu, QAction
)
from PyQt5.QtGui import (
    QPainter, QPen, QColor, QFont, QPixmap, QLinearGradient, QBrush, QPainterPath
)
from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve, pyqtProperty, pyqtSignal

from app.desktop.threads.thumbnail_loader import ThumbnailLoader
from app.desktop.utils.metadata import get_audio_metadata


class PlaylistCard(QFrame):
    """Spotify-style playlist card with cover grid"""

    delete_requested = pyqtSignal(str)  # folder_path
    play_requested   = pyqtSignal(str)  # folder_path
    random_play_requested = pyqtSignal(str)  # folder_path — play random track
    open_requested   = pyqtSignal(str)  # folder_path — emitted on single click

    COVER_TILE = 66

    @staticmethod
    def _square_tile(pixmap: QPixmap, size: int) -> QPixmap:
        """Center-crop to a rounded square (same pipeline as album / queue thumbs)."""
        if pixmap.isNull():
            return pixmap
        scaled = pixmap.scaled(
            size,
            size,
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation,
        )
        out = QPixmap(size, size)
        out.fill(Qt.transparent)
        p = QPainter(out)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, size, size, 6, 6)
        p.setClipPath(path)
        x = (scaled.width() - size) // 2
        y = (scaled.height() - size) // 2
        p.drawPixmap(-x, -y, scaled)
        p.end()
        return out

    def __init__(self, folder_path, parent=None):
        super().__init__(parent)
        
        self.folder_path = folder_path
        self.folder_name = os.path.basename(folder_path)
        self.hovered = False
        self.thumbnail_loader: Optional[ThumbnailLoader] = None
        self.song_covers = []
        
        self.colors = {
            'bg': '#181818',
            'bg_hover': '#282828',
            'text_primary': '#FFFFFF',
            'text_secondary': '#B3B3B3',
            'accent': '#1DB954',
        }
        
        self.setup_ui()
        self.load_playlist_info()
        self.update_style()
        
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumWidth(180)
        self.setMaximumWidth(240)
        self.setMinimumHeight(220)
        
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

    def setup_ui(self):
        """Setup UI for Spotify-style playlist card"""
        self.setObjectName("playlist_card")
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(8)
        
        # Cover grid container
        cover_container = QFrame()
        cover_container.setFixedHeight(140)
        cover_container.setStyleSheet(f"""
            background-color: {self.colors['bg']};
            border-radius: 6px;
        """)
        
        # Create 2x2 grid of cover images
        self.cover_layout = QGridLayout(cover_container)
        self.cover_layout.setContentsMargins(4, 4, 4, 4)
        self.cover_layout.setSpacing(2)
        
        # Create 4 placeholder cover labels
        self.cover_labels = []
        for i in range(4):
            row = i // 2
            col = i % 2
            cover_label = QLabel()
            cover_label.setFixedSize(self.COVER_TILE, self.COVER_TILE)
            cover_label.setStyleSheet("border-radius: 4px;")
            self.cover_layout.addWidget(cover_label, row, col)
            self.cover_labels.append(cover_label)
        
        main_layout.addWidget(cover_container)
        
        # Play button overlay
        self.play_btn = QPushButton("▶")
        self.play_btn.setFixedSize(40, 40)
        self.play_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.colors['accent']};
                color: #000000;
                border: none;
                border-radius: 20px;
                font-size: 18px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #1ED760;
            }}
        """)
        self.play_btn.setVisible(False)
        self.play_btn.raise_()  # Ensure it's on top
        self.play_btn.clicked.connect(self.on_play_clicked)

        self.random_btn = QPushButton("🎲")
        self.random_btn.setFixedSize(32, 32)
        self.random_btn.setToolTip("Play random song from playlist")
        self.random_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(255,255,255,0.12);
                color: #e8eaf0;
                border: none;
                border-radius: 16px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: rgba(255,255,255,0.22);
            }}
        """)
        self.random_btn.setVisible(False)
        self.random_btn.setParent(self)
        self.random_btn.clicked.connect(self._on_random_clicked)
        
        # Text content container
        text_container = QWidget()
        text_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        text_layout = QVBoxLayout(text_container)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(4)
        
        # Playlist name
        self.name_label = QLabel(self.folder_name)
        self.name_label.setStyleSheet(f"""
            color: {self.colors['text_primary']};
            font-size: 14px;
            font-weight: 600;
            padding-top: 4px;
        """)
        self.name_label.setWordWrap(True)
        self.name_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        text_layout.addWidget(self.name_label)
        
        # Song count
        self.count_label = QLabel("0 songs")
        self.count_label.setStyleSheet(f"""
            color: {self.colors['text_secondary']};
            font-size: 12px;
        """)
        text_layout.addWidget(self.count_label)
        
        main_layout.addWidget(text_container)
        
        # Set play button as a child of this widget
        self.play_btn.setParent(self)
    
    def on_play_clicked(self):
        """Handle play button click"""
        self.play_requested.emit(self.folder_path)

    def _on_random_clicked(self):
        self.random_play_requested.emit(self.folder_path)
    
    def show_context_menu(self, position):
        """Show context menu for playlist card"""
        menu = QMenu(self)
        
        # Play action
        play_action = QAction("▶ Play", self)
        play_action.triggered.connect(self.on_play_clicked)
        menu.addAction(play_action)
        rand_action = QAction("🎲 Random song", self)
        rand_action.triggered.connect(self._on_random_clicked)
        menu.addAction(rand_action)
        
        menu.addSeparator()
        
        # Delete action
        delete_action = QAction("🗑️ Delete Playlist", self)
        delete_action.triggered.connect(self.on_delete_clicked)
        menu.addAction(delete_action)
        
        menu.exec_(self.mapToGlobal(position))
    
    def on_delete_clicked(self):
        """Handle delete playlist request"""
        self.delete_requested.emit(self.folder_path)
    
    def resizeEvent(self, event):
        """Handle resize to position play + random buttons"""
        super().resizeEvent(event)
        btn_y = 12 + 140 - 50
        self.random_btn.move(self.width() - 90, btn_y)
        self.play_btn.move(self.width() - 48, btn_y)
        self.random_btn.raise_()
        self.play_btn.raise_()
    
    def load_playlist_info(self):
        """Load playlist information from JSON"""
        print(f"[DEBUG] Loading playlist info for: {self.folder_path}")
        
        if not os.path.exists(self.folder_path):
            print(f"[DEBUG] Playlist folder does not exist: {self.folder_path}")
            self.set_placeholder_covers()
            return
        
        # Try to read playlist JSON
        json_path = os.path.join(self.folder_path, "playlist.json")
        
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    playlist_data = json.load(f)
                
                song_count = len(playlist_data.get("songs", []))
                self.count_label.setText(f"{song_count} song{'s' if song_count != 1 else ''}")
                
                # Load covers from first 4 songs
                songs = playlist_data.get("songs", [])[:4]
                
                for i, song in enumerate(songs):
                    if i < len(self.cover_labels):
                        self.load_song_cover(i, song)
                
                # Fill remaining slots with placeholders
                for i in range(len(songs), 4):
                    self.set_single_placeholder(i)
                
                return
                
            except Exception as e:
                print(f"[ERROR] Error reading playlist JSON: {e}")
        
        # Fallback: scan folder for audio files
        self.load_playlist_covers_legacy()
    
    def load_playlist_covers_legacy(self):
        """Legacy method to load covers by scanning folder"""
        if not os.path.exists(self.folder_path):
            self.set_placeholder_covers()
            return
        
        try:
            audio_files = []
            for root, dirs, files in os.walk(self.folder_path):
                for file in files:
                    if file.lower().endswith(('.mp3', '.mp4', '.m4a', '.flac', '.wav', '.ogg')):
                        audio_files.append(os.path.join(root, file))
            
            print(f"[DEBUG] Found {len(audio_files)} audio files in playlist")
            
            song_count = len(audio_files)
            self.count_label.setText(f"{song_count} song{'s' if song_count != 1 else ''}")
            
            if not audio_files:
                self.set_placeholder_covers()
                return
            
            # Load covers from first 4 songs
            for i in range(min(4, len(audio_files))):
                if i < len(self.cover_labels):
                    self.load_song_cover_legacy(i, audio_files[i])
            
            # Fill remaining slots with placeholders
            for i in range(len(audio_files), 4):
                self.set_single_placeholder(i)
            
        except Exception as e:
            print(f"[ERROR] Error loading playlist covers: {e}")
            self.set_placeholder_covers()
    
    def load_song_cover(self, index, song_data):
        """Load cover for a song from JSON data"""
        file_path = song_data.get("file_path")
        
        if file_path and os.path.exists(file_path):
            try:
                metadata = get_audio_metadata(file_path)
                if metadata.get("has_cover") and metadata.get("cover_base64"):
                    import base64
                    from PyQt5.QtGui import QImage, QPixmap
                    
                    # Decode base64 image
                    image_data = base64.b64decode(metadata["cover_base64"])
                    
                    # Create QImage from data
                    image = QImage()
                    image.loadFromData(image_data)
                    
                    # Create pixmap
                    pixmap = QPixmap.fromImage(image)
                    
                    tile = self._square_tile(pixmap, self.COVER_TILE)
                    self.cover_labels[index].setPixmap(tile)
                    return
            except Exception as e:
                print(f"[DEBUG] Error loading cover from metadata: {e}")
        
        # Fallback to color based on index
        colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4']
        color = colors[index % len(colors)]
        self.set_single_placeholder(index, color)
    
    def load_song_cover_legacy(self, index, file_path):
        """Legacy method to load cover from file"""
        try:
            metadata = get_audio_metadata(file_path)
            
            if metadata.get("has_cover") and metadata.get("cover_base64"):
                import base64
                from PyQt5.QtGui import QImage, QPixmap
                
                # Decode base64 image
                image_data = base64.b64decode(metadata["cover_base64"])
                
                # Create QImage from data
                image = QImage()
                image.loadFromData(image_data)
                
                # Create pixmap
                pixmap = QPixmap.fromImage(image)
                
                tile = self._square_tile(pixmap, self.COVER_TILE)
                self.cover_labels[index].setPixmap(tile)
                return
        except Exception as e:
            print(f"[DEBUG] Error loading cover from file: {e}")
        
        # Fallback to color based on index
        colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4']
        color = colors[index % len(colors)]
        self.set_single_placeholder(index, color)
    
    def set_single_placeholder(self, index, color=None):
        """Set single placeholder cover"""
        if index >= len(self.cover_labels):
            return
        
        if color is None:
            colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4']
            color = colors[index % len(colors)]
        
        pixmap = QPixmap(66, 66)
        pixmap.fill(QColor(color))
        
        painter = QPainter(pixmap)
        if painter.isActive():
            painter.setRenderHint(QPainter.Antialiasing)
            
            # Add note symbol or number
            painter.setPen(QPen(QColor('#FFFFFF'), 2))
            painter.setFont(QFont("Arial", 16, QFont.Bold))
            
            # Draw note symbol or number
            if index < 4:
                painter.drawText(pixmap.rect(), Qt.AlignCenter, "♪")
            else:
                painter.drawText(pixmap.rect(), Qt.AlignCenter, str(index+1))
            
            painter.end()
        
        self.cover_labels[index].setPixmap(pixmap)
        self.cover_labels[index].setStyleSheet(f"border-radius: 6px;")
    
    def set_placeholder_covers(self):
        """Set placeholder cover images for all slots"""
        colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4']
        
        for i, cover_label in enumerate(self.cover_labels):
            color = colors[i % len(colors)]
            self.set_single_placeholder(i, color)
    
    def on_thumbnail_loader_finished(self):
        """Handle thumbnail loader finishing"""
        if self.thumbnail_loader:
            try:
                self.thumbnail_loader.loaded.disconnect()
                self.thumbnail_loader.error.disconnect()
                self.thumbnail_loader.finished.disconnect()
            except:
                pass
            self.thumbnail_loader = None
    
    def cleanup_thumbnail_loader(self):
        """Clean up thumbnail loader resources"""
        if self.thumbnail_loader:
            if self.thumbnail_loader.isRunning():
                self.thumbnail_loader.stop()
            
            try:
                self.thumbnail_loader.loaded.disconnect()
                self.thumbnail_loader.error.disconnect()
                self.thumbnail_loader.finished.disconnect()
            except:
                pass
            
            self.thumbnail_loader = None
    
    def enterEvent(self, event):
        """Handle mouse enter"""
        self.hovered = True
        self.update_style()
        self.animate_hover()
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        """Handle mouse leave"""
        self.hovered = False
        self.update_style()
        self.animate_leave()
        super().leaveEvent(event)
    
    def animate_hover(self):
        """Animate hover effect"""
        self.play_btn.setVisible(True)
        self.random_btn.setVisible(True)
        
        # Scale animation
        animation = QPropertyAnimation(self, b"geometry")
        animation.setDuration(200)
        animation.setStartValue(self.geometry())
        animation.setEndValue(self.geometry().adjusted(-3, -3, 3, 3))
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.start()
    
    def animate_leave(self):
        """Animate leave effect"""
        self.play_btn.setVisible(False)
        self.random_btn.setVisible(False)
        
        animation = QPropertyAnimation(self, b"geometry")
        animation.setDuration(200)
        animation.setStartValue(self.geometry())
        animation.setEndValue(self.geometry().adjusted(3, 3, -3, -3))
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.start()
    
    def update_style(self):
        """Update visual style"""
        if self.hovered:
            bg_color = self.colors['bg_hover']
            border_color = self.colors['text_secondary']
            border_width = "1px"
        else:
            bg_color = self.colors['bg']
            border_color = self.colors['bg']
            border_width = "1px"
        
        self.setStyleSheet(f"""
            QFrame#playlist_card {{
                background-color: {bg_color};
                border: {border_width} solid {border_color};
                border-radius: 8px;
            }}
        """)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.open_requested.emit(self.folder_path)
        super().mousePressEvent(event)

    def cleanup(self):
        """Clean up all resources"""
        self.cleanup_thumbnail_loader()