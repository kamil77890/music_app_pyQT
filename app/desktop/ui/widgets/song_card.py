"""
Song card widget for Spotify-style layout with fixed size
"""

import os
from typing import Optional
from PyQt5.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
    QWidget
)
from PyQt5.QtGui import (
    QPainter, QPen, QColor, QFont, QPixmap, QLinearGradient, QBrush
)
from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve, pyqtProperty, QSize

from app.desktop.utils.helpers import get_field
from app.desktop.threads.thumbnail_loader import ThumbnailLoader


class SongCard(QFrame):
    """Spotify-style song card with fixed size"""
    
    def __init__(self, entry, parent=None):
        super().__init__(parent)
        
        if entry is None:
            raise ValueError("Entry cannot be None")
            
        self.entry = entry
        self.selected = False
        self.hovered = False
        self.download_status = None
        self.thumbnail_loader: Optional[ThumbnailLoader] = None
        
        self.colors = {
            'bg': '#181818',
            'bg_hover': '#282828',
            'text_primary': '#FFFFFF',
            'text_secondary': '#B3B3B3',
            'accent': '#1DB954',
        }
        
        self.setup_ui()
        self.load_thumbnail()
        self.update_style()
        
        self.setFixedSize(180, 240)
        
    def setup_ui(self):
        self.setObjectName("song_card")
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(8)
        
        art_container = QFrame()
        art_container.setFixedHeight(140)
        art_container.setStyleSheet(f"""
            background-color: {self.colors['bg']};
            border-radius: 6px;
        """)
        
        art_layout = QVBoxLayout(art_container)
        art_layout.setContentsMargins(0, 0, 0, 0)
        
        self.thumb_label = QLabel()
        self.thumb_label.setAlignment(Qt.AlignCenter)
        self.thumb_label.setScaledContents(True)
        self.thumb_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.thumb_label.setStyleSheet("border-radius: 6px;")
        art_layout.addWidget(self.thumb_label)
        
        main_layout.addWidget(art_container)
        
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
        self.play_btn.raise_()
        
        text_container = QWidget()
        text_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        text_layout = QVBoxLayout(text_container)
        text_layout.setContentsMargins(2, 0, 0, 0)
        text_layout.setSpacing(8)
        
        title = get_field(self.entry, "title", "Unknown Title")
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(f"""
            color: {self.colors['text_primary']};
            font-size: 11px;
            font-weight: 600;
            padding: 4px;
        """)
        self.title_label.setWordWrap(True)
        self.title_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        text_layout.addWidget(self.title_label)
        
        artist = get_field(self.entry, "artist", "Unknown Artist")
        self.artist_label = QLabel(artist)
        self.artist_label.setStyleSheet(f"""
            color: {self.colors['text_secondary']};
            font-size: 9px;
        """)
        self.artist_label.setWordWrap(True)
        self.artist_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.artist_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        text_container.setStyleSheet(f"""
            background-color: 'transparent';
            border-radius: 6px;
        """)
        text_layout.addWidget(self.artist_label)
        
        main_layout.addWidget(text_container)
        
        self.play_btn.setParent(self)
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        btn_y = 12 + 140 - 50
        btn_x = self.width() - 52
        self.play_btn.move(btn_x, btn_y)
    
    def load_thumbnail(self):
        thumb_url = (
            get_field(self.entry, "cover", "")
            or get_field(self.entry, "thumbnail", "")
        )
        
        if not thumb_url:
            self.set_placeholder()
            return
        
        self.cleanup_thumbnail_loader()
        
        self.thumbnail_loader = ThumbnailLoader(thumb_url)
        self.thumbnail_loader.loaded.connect(self.set_thumbnail)
        self.thumbnail_loader.error.connect(self.set_placeholder)
        self.thumbnail_loader.finished.connect(self.on_thumbnail_loader_finished)
        self.thumbnail_loader.start()
    
    def set_thumbnail(self, pixmap: QPixmap):
        if not pixmap.isNull():
            size = 140
            scaled = pixmap.scaled(
                size, size,
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation
            )
            self.thumb_label.setPixmap(scaled)
    
    def set_placeholder(self):
        size = 140
        pixmap = QPixmap(size, size)
        pixmap.fill(QColor(self.colors['bg']))
        
        painter = QPainter(pixmap)
        if painter.isActive():
            painter.setRenderHint(QPainter.Antialiasing)
            
            gradient = QLinearGradient(0, 0, size, size)
            gradient.setColorAt(0, QColor('#333333'))
            gradient.setColorAt(1, QColor('#666666'))
            painter.setBrush(QBrush(gradient))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(0, 0, size, size, 6, 6)
            
            painter.setPen(QPen(QColor(self.colors['text_secondary'])))
            font_size = 36
            painter.setFont(QFont("Arial", font_size, QFont.Bold))
            painter.drawText(pixmap.rect(), Qt.AlignCenter, "♪")
            
            painter.end()
        
        self.thumb_label.setPixmap(pixmap)
    
    def on_thumbnail_loader_finished(self):
        if self.thumbnail_loader:
            try:
                self.thumbnail_loader.loaded.disconnect()
                self.thumbnail_loader.error.disconnect()
                self.thumbnail_loader.finished.disconnect()
            except:
                pass
            self.thumbnail_loader = None
    
    def cleanup_thumbnail_loader(self):
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
    
    def set_download_status(self, status: str):
        self.download_status = status
        
        status_colors = {
            'success': '#1DB954',
            'failed': '#E22134',
            'exists': '#FFD700',
            'downloading': '#1DB954'
        }
        
        if status in status_colors:
            self.play_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {status_colors[status]};
                    color: #000000;
                    border: none;
                    border-radius: 20px;
                    font-size: 18px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {status_colors[status]};
                    opacity: 0.9;
                }}
            """)
            
            if status == 'downloading':
                self.play_btn.setText("⟳")
            elif status == 'exists':
                self.play_btn.setText("✓")
            elif status == 'failed':
                self.play_btn.setText("✗")
            else:
                self.play_btn.setText("▶")
            
            self.play_btn.setVisible(True)
    
    def set_selected(self, selected: bool):
        self.selected = selected
        self.update_style()
        
        if selected:
            self.animate_select()
        else:
            self.animate_deselect()
    
    def animate_select(self):
        animation = QPropertyAnimation(self, b"geometry")
        animation.setDuration(150)
        animation.setStartValue(self.geometry())
        animation.setEndValue(self.geometry().adjusted(-2, -2, 2, 2))
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.start()
    
    def animate_deselect(self):
        animation = QPropertyAnimation(self, b"geometry")
        animation.setDuration(150)
        animation.setStartValue(self.geometry())
        animation.setEndValue(self.geometry().adjusted(2, 2, -2, -2))
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.start()
    
    def enterEvent(self, event):
        self.hovered = True
        self.update_style()
        self.animate_hover()
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        self.hovered = False
        self.update_style()
        self.animate_leave()
        super().leaveEvent(event)
    
    def animate_hover(self):
        self.play_btn.setVisible(True)
        
        animation = QPropertyAnimation(self, b"geometry")
        animation.setDuration(200)
        animation.setStartValue(self.geometry())
        animation.setEndValue(self.geometry().adjusted(-3, -3, 3, 3))
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.start()
    
    def animate_leave(self):
        if not self.selected and not self.download_status:
            self.play_btn.setVisible(False)
        
        animation = QPropertyAnimation(self, b"geometry")
        animation.setDuration(200)
        animation.setStartValue(self.geometry())
        
        if self.selected:
            target = self.geometry().adjusted(-2, -2, 2, 2)
        else:
            target = self.geometry().adjusted(3, 3, -3, -3)
        
        animation.setEndValue(target)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.start()
    
    def update_style(self):
        if self.selected:
            bg_color = self.colors['bg_hover']
            border_color = self.colors['accent']
            border_width = "2px"
        elif self.hovered:
            bg_color = self.colors['bg_hover']
            border_color = self.colors['text_secondary']
            border_width = "1px"
        else:
            bg_color = self.colors['bg']
            border_color = self.colors['bg']
            border_width = "1px"
        
        self.setStyleSheet(f"""
            QFrame#song_card {{
                background-color: {bg_color};
                border: {border_width} solid {border_color};
                border-radius: 8px;
            }}
        """)
    
    def cleanup(self):
        self.cleanup_thumbnail_loader()