
from PyQt5.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QListWidget, QListWidgetItem, QScrollArea
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QCursor


class PlaylistWidget(QFrame):
    
    song_clicked = pyqtSignal(str, dict)  # file_path, metadata
    playlist_updated = pyqtSignal(list)  # Updated playlist
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.playlist_data = []  # List of (file_path, metadata) tuples
        self.current_playing_index = -1
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the UI elements"""
        self.setMinimumWidth(300)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # Header
        header = QFrame()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        title = QLabel("🎵 Playlist")
        title.setProperty("title", True)
        
        self.clear_btn = QPushButton("Clear All")
        self.clear_btn.setFixedSize(80, 25)
        self.clear_btn.clicked.connect(self.clear)
        
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(self.clear_btn)
        
        layout.addWidget(header)
        
        # Playlist items
        self.playlist_list = QListWidget()
        self.playlist_list.setAlternatingRowColors(True)
        
        # Connect double-click signal
        self.playlist_list.itemDoubleClicked.connect(self.on_item_double_clicked)
        # Connect single-click signal (optional, if you want play on single click)
        self.playlist_list.itemClicked.connect(self.on_item_clicked)
        
        layout.addWidget(self.playlist_list)
        
        # Info
        self.info_label = QLabel("0 songs in playlist")
        self.info_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.info_label)
    
    def add_song(self, file_path, metadata=None):
        """Add a song to the playlist"""
        if metadata is None:
            metadata = {}
            
        # Add to internal data
        self.playlist_data.append((file_path, metadata))
        
        # Create display text
        title = metadata.get('title', 'Unknown Title')
        artist = metadata.get('artist', 'Unknown Artist')
        item_text = f"{title} - {artist}"
        
        # Add to list widget
        item = QListWidgetItem(item_text)
        item.setData(Qt.UserRole, (file_path, metadata))
        item.setToolTip(f"Click to play: {title}")
        self.playlist_list.addItem(item)
        
        self.update_info()
        self.playlist_updated.emit(self.playlist_data)

    
    
    def on_item_double_clicked(self, item):
        """Handle double-click on playlist item"""
        file_path, metadata = item.data(Qt.UserRole)
        self.set_current_playing(self.playlist_list.row(item))
        self.song_clicked.emit(file_path, metadata)
    
    def on_item_clicked(self, item):
        """Handle single-click on playlist item (optional)"""
        # You can use this for selection or other actions
        pass
    
    def set_current_playing(self, index):
        """Set the currently playing song visually"""
        # Clear previous current playing style
        for i in range(self.playlist_list.count()):
            item = self.playlist_list.item(i)
            if item:
                item.setBackground(Qt.transparent)
                # Reset text color if needed
                # item.setForeground(Qt.white)
        
        # Set new current playing
        if 0 <= index < self.playlist_list.count():
            item = self.playlist_list.item(index)
            if item:
                item.setBackground(Qt.darkBlue)  # Or use style sheet class
                self.playlist_list.setCurrentRow(index)
                self.current_playing_index = index
    
    def remove_current(self):
        """Remove currently selected song"""
        current_row = self.playlist_list.currentRow()
        if current_row >= 0:
            self.playlist_list.takeItem(current_row)
            self.playlist_data.pop(current_row)
            
            # Update current playing index if needed
            if self.current_playing_index == current_row:
                self.current_playing_index = -1
            elif self.current_playing_index > current_row:
                self.current_playing_index -= 1
                
            self.update_info()
            self.playlist_updated.emit(self.playlist_data)
    
    def clear(self):
        """Clear all songs from playlist"""
        self.playlist_list.clear()
        self.playlist_data.clear()
        self.current_playing_index = -1
        self.update_info()
        self.playlist_updated.emit([])
    
    def update_info(self):
        """Update information label"""
        count = self.playlist_list.count()
        self.info_label.setText(f"{count} song{'s' if count != 1 else ''} in playlist")
    
    def get_playlist(self):
        """Get the current playlist data"""
        return self.playlist_data.copy()
    
    def get_next_song(self):
        """Get the next song in playlist"""
        if not self.playlist_data or self.current_playing_index == -1:
            return None
        
        next_index = self.current_playing_index + 1
        if next_index < len(self.playlist_data):
            return self.playlist_data[next_index]
        return None
    
    def get_previous_song(self):
        """Get the previous song in playlist"""
        if not self.playlist_data or self.current_playing_index <= 0:
            return None
        
        prev_index = self.current_playing_index - 1
        if prev_index >= 0:
            return self.playlist_data[prev_index]
        return None