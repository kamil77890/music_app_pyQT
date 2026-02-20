"""
Download manager item widget
"""

import os
import sys
from PyQt5.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
)
from PyQt5.QtCore import Qt
from app.desktop.utils.metadata import get_mp3_metadata

class DownloadManagerItem(QFrame):
    """Widget for displaying downloaded songs in the right panel"""
    
    def __init__(self, file_path: str, metadata: dict = None, status: str = "completed", main_window=None):
        super().__init__()
        self.file_path = file_path
        self.metadata = metadata or {}
        self.status = status
        self.main_window = main_window
        
        self.setup_ui()
        self.update_style()
    
    def setup_ui(self):
        """Setup the UI elements"""
        self.setFixedHeight(80)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(12)
        
        # Status icon
        self.status_icon = QLabel()
        self.status_icon.setFixedSize(24, 24)
        layout.addWidget(self.status_icon)
        
        # Song info
        info_widget = QFrame()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(4)
        
        # Title
        title = self.metadata.get('title', os.path.basename(self.file_path).replace('.mp3', ''))
        self.title_label = QLabel(title)
        self.title_label.setWordWrap(True)
        info_layout.addWidget(self.title_label)
        
        # Details
        artist = self.metadata.get('artist', 'Unknown Artist')
        duration = self.metadata.get('duration', 0)
        
        # Format duration
        if duration > 0:
            minutes = duration // 60
            seconds = duration % 60
            duration_str = f" • {minutes}:{seconds:02d}"
        else:
            duration_str = ""
        
        self.details_label = QLabel(f"{artist}{duration_str}")
        info_layout.addWidget(self.details_label)
        info_layout.addStretch()
        
        layout.addWidget(info_widget, 1)
        
        # Action buttons
        btn_container = QFrame()
        btn_layout = QVBoxLayout(btn_container)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(4)
        
        # Open file button
        self.open_btn = QPushButton("📂")
        self.open_btn.setFixedSize(30, 30)
        self.open_btn.setToolTip("Open file location")
        self.open_btn.clicked.connect(self.open_file_location)
        
        # Play button
        self.play_btn = QPushButton("▶")
        self.play_btn.setFixedSize(30, 30)
        self.play_btn.setToolTip("Play file")
        self.play_btn.clicked.connect(self.play_file)
        
        btn_layout.addWidget(self.play_btn)
        btn_layout.addWidget(self.open_btn)
        layout.addWidget(btn_container)
    
    def update_style(self):
        """Update visual style based on status"""
        status_icons = {
            'completed': '✓',
            'failed': '✗',
            'downloading': '⟳',
            'exists': '✓'
        }
        
        icon = status_icons.get(self.status, '?')
        self.status_icon.setText(icon)
    
    def open_file_location(self):
        """Open file in system file explorer"""
        try:
            if os.path.exists(self.file_path):
                if sys.platform == "win32":
                    os.startfile(os.path.dirname(self.file_path))
                elif sys.platform == "darwin":
                    import subprocess
                    subprocess.Popen(["open", os.path.dirname(self.file_path)])
                else:
                    import subprocess
                    subprocess.Popen(["xdg-open", os.path.dirname(self.file_path)])
        except Exception as e:
            print(f"Error opening file location: {e}")
    
    def play_file(self):
        """Play the audio file"""
        if self.main_window and hasattr(self.main_window, 'play_song_from_manager'):
            self.main_window.play_song_from_manager(self.file_path, self.metadata)
    
    def mouseDoubleClickEvent(self, event):
        """Handle double click to play song"""
        self.play_file()
        event.accept()