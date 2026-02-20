# library_view.py
"""
Library view widget showing songs with covers, titles, and authors in a grid
"""

import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QGridLayout, QLineEdit, QPushButton, QMessageBox
)
from PyQt5.QtCore import Qt, pyqtSignal
from app.desktop.config import config
from app.desktop.utils.helpers import get_mp3_files_recursive
from app.desktop.utils.metadata import get_mp3_metadata
from app.desktop.utils.playlist_manager import PlaylistManager


class LibraryViewWidget(QWidget):
    
    song_double_clicked = pyqtSignal(str, dict)
    playlist_selected = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_folder = ""
        self.all_songs = []  # Store all songs for filtering
        self.song_cards = []  # Store song card widgets
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the UI elements"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header with folder name and search
        self.header_widget = QFrame()
        self.header_widget.setFixedHeight(50)
        self.header_widget.setProperty("header", True)
        
        header_layout = QHBoxLayout(self.header_widget)
        header_layout.setContentsMargins(15, 0, 15, 0)
        
        self.folder_label = QLabel("Music Library")
        
        # Search bar for library
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search songs...")
        self.search_input.setFixedWidth(200)
        self.search_input.textChanged.connect(self.filter_songs)
        
        # Add to playlist button
        self.add_to_playlist_btn = QPushButton("+ Add to Playlist")
        self.add_to_playlist_btn.setFixedWidth(120)
        self.add_to_playlist_btn.clicked.connect(self.add_selected_to_playlist)
        self.add_to_playlist_btn.setEnabled(False)
        
        self.song_count = QLabel("0 songs")
        
        header_layout.addWidget(self.folder_label)
        header_layout.addStretch()
        header_layout.addWidget(self.search_input)
        header_layout.addSpacing(10)
        header_layout.addWidget(self.add_to_playlist_btn)
        header_layout.addSpacing(10)
        header_layout.addWidget(self.song_count)
        
        layout.addWidget(self.header_widget)
        
        # Song grid area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setContentsMargins(15, 15, 15, 15)
        self.grid_layout.setSpacing(15)
        self.grid_layout.setAlignment(Qt.AlignTop)
        
        self.scroll_area.setWidget(self.grid_widget)
        layout.addWidget(self.scroll_area, 1)
        
        # Empty state
        self.empty_state = QLabel("No songs found in this folder")
        self.empty_state.setAlignment(Qt.AlignCenter)
        self.empty_state.hide()
        layout.addWidget(self.empty_state)
        
        # Selected songs tracking
        self.selected_songs = set()
    
    def set_folder_name(self, folder_name):
        """Set the folder name in the header"""
        self.folder_label.setText(f"📁 {folder_name}")
    
    def load_folder(self, folder_path):
        """Load songs from a folder"""
        self.current_folder = folder_path
        self.all_songs = []
        self.clear_song_cards()
        self.selected_songs.clear()
        self.add_to_playlist_btn.setEnabled(False)
        
        if not folder_path or not os.path.exists(folder_path):
            self.show_empty_state("Folder not found")
            return
        
        # Get all MP3 files recursively
        try:
            mp3_files = get_mp3_files_recursive(folder_path)
        except Exception as e:
            print(f"Error reading folder {folder_path}: {e}")
            self.show_empty_state("Error reading folder")
            return
        
        if not mp3_files:
            self.show_empty_state("No songs found in this folder")
            return
        
        # Load metadata and create song entries
        for file_path in mp3_files:
            try:
                metadata = get_mp3_metadata(file_path)
                title = metadata.get('title', os.path.basename(file_path).replace('.mp3', ''))
                artist = metadata.get('artist', 'Unknown Artist')
                album = metadata.get('album', 'Unknown Album')
                duration = metadata.get('duration', 0)
                has_cover = metadata.get('has_cover', False)
                
                song_entry = {
                    'title': title,
                    'artist': artist,
                    'album': album,
                    'duration': duration,
                    'cover': None,
                    'file_path': file_path,
                    'metadata': metadata
                }
                
                self.all_songs.append(song_entry)
            except Exception as e:
                print(f"Error loading song {file_path}: {e}")
                continue
        
        # Display filtered songs
        self.filter_songs()
    
    def clear_song_cards(self):
        """Clear all song cards"""
        for card in self.song_cards:
            try:
                card.deleteLater()
            except:
                pass
        self.song_cards.clear()
        
        # Clear grid layout
        for i in reversed(range(self.grid_layout.count())):
            widget = self.grid_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()
    
    def filter_songs(self):
        """Filter songs based on search text"""
        search_text = self.search_input.text().lower().strip()
        
        # Clear current cards
        self.clear_song_cards()
        self.selected_songs.clear()
        self.add_to_playlist_btn.setEnabled(False)
        
        # Filter songs
        filtered_songs = []
        for song in self.all_songs:
            title = song['title'].lower()
            artist = song['artist'].lower()
            album = song['album'].lower()
            
            if not search_text or search_text in title or search_text in artist or search_text in album:
                filtered_songs.append(song)
        
        # Display filtered songs in grid
        if filtered_songs:
            self.empty_state.hide()
            self.scroll_area.show()
            
            # Add song cards to grid
            columns = 3  # Number of columns in the grid
            for i, song in enumerate(filtered_songs):
                row = i // columns
                col = i % columns
                
                # Create a library song card
                card = self.create_library_card(song, i)
                self.grid_layout.addWidget(card, row, col)
                self.song_cards.append(card)
            
            # Update count
            self.song_count.setText(f"{len(filtered_songs)} song{'s' if len(filtered_songs) != 1 else ''}")
        else:
            self.show_empty_state(f"No songs match '{search_text}'")
    
    def create_library_card(self, song, index):
        """Create a library song card widget with selection support"""
        from PyQt5.QtWidgets import QFrame, QVBoxLayout, QLabel, QCheckBox
        from PyQt5.QtGui import QPixmap, QPainter, QPen, QColor, QFont
        from PyQt5.QtCore import Qt
        
        card = QFrame()
        card.setFixedSize(180, 220)
        card.setObjectName("song_card")
        card.setProperty("song_index", index)
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        
        # Selection checkbox
        checkbox = QCheckBox()
        checkbox.setChecked(False)
        checkbox.stateChanged.connect(lambda state, idx=index: self.on_song_selected(idx, state))
        layout.addWidget(checkbox, 0, Qt.AlignRight)
        
        # Album art
        album_art = QLabel()
        album_art.setFixedSize(160, 120)
        
        # Create placeholder art
        pixmap = QPixmap(160, 120)
        pixmap.fill(QColor("#1a1a2e"))
        painter = QPainter(pixmap)
        if painter.isActive():
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(QPen(QColor("#2a6fc1"), 2))
            painter.drawRoundedRect(2, 2, 156, 116, 4, 4)
            painter.setPen(QPen(QColor("#3a7fd1"), 1))
            painter.setFont(QFont("Arial", 36, QFont.Bold))
            painter.drawText(pixmap.rect(), Qt.AlignCenter, "♪")
            painter.end()
        album_art.setPixmap(pixmap)
        
        layout.addWidget(album_art)
        
        # Song title
        title_label = QLabel(song['title'][:30] + "..." if len(song['title']) > 30 else song['title'])
        title_label.setWordWrap(True)
        title_label.setMaximumHeight(40)
        layout.addWidget(title_label)
        
        # Artist
        artist_label = QLabel(song['artist'][:25] + "..." if len(song['artist']) > 25 else song['artist'])
        layout.addWidget(artist_label)
        
        # Album (if available)
        if song['album'] and song['album'] != 'Unknown Album':
            album_label = QLabel(song['album'][:20] + "..." if len(song['album']) > 20 else song['album'])
            layout.addWidget(album_label)
        
        layout.addStretch()
        
        # Connect double-click
        def on_double_click(event):
            if event.button() == Qt.LeftButton:
                self.song_double_clicked.emit(song['file_path'], song['metadata'])
        
        card.mouseDoubleClickEvent = on_double_click
        
        return card
    
    def on_song_selected(self, index, state):
        """Handle song selection"""
        if state == Qt.Checked:
            self.selected_songs.add(index)
        else:
            self.selected_songs.discard(index)
        
        # Update add to playlist button
        self.add_to_playlist_btn.setEnabled(len(self.selected_songs) > 0)
    
    def add_selected_to_playlist(self):
        """Add selected songs to a playlist"""
        if not self.selected_songs:
            return
        
        # Get selected songs
        selected_song_data = []
        for index in self.selected_songs:
            if 0 <= index < len(self.all_songs):
                song = self.all_songs[index]
                selected_song_data.append(song)
        
        if not selected_song_data:
            return
        
        # Get available playlists
        download_path = config.get_download_path()
        playlists = PlaylistManager.get_all_playlists(download_path)
        
        if not playlists:
            QMessageBox.information(self, "No Playlists", 
                                  "Create a playlist first to add songs.")
            return
        
        # Show playlist selection dialog
        from PyQt5.QtWidgets import QInputDialog
        
        playlist_names = [p["name"] for p in playlists]
        playlist_name, ok = QInputDialog.getItem(
            self, "Add to Playlist",
            f"Select playlist for {len(selected_song_data)} song(s):",
            playlist_names, 0, False
        )
        
        if ok and playlist_name:
            # Find selected playlist
            for playlist in playlists:
                if playlist["name"] == playlist_name:
                    added_count = 0
                    
                    for song_data in selected_song_data:
                        file_path = song_data['file_path']
                        metadata = song_data['metadata']
                        
                        if PlaylistManager.add_song_to_playlist(
                            playlist["folder_path"], 
                            file_path, 
                            metadata
                        ):
                            added_count += 1
                    
                    QMessageBox.information(
                        self, "Songs Added",
                        f"Added {added_count} song(s) to '{playlist_name}' playlist."
                    )
                    
                    # Clear selection
                    self.selected_songs.clear()
                    self.add_to_playlist_btn.setEnabled(False)
                    
                    # Update checkboxes
                    for card in self.song_cards:
                        checkbox = card.findChild(QCheckBox)
                        if checkbox:
                            checkbox.setChecked(False)
                    
                    break
    
    def show_empty_state(self, message):
        """Show empty state message"""
        self.empty_state.setText(message)
        self.empty_state.show()
        self.scroll_area.hide()
        self.song_count.setText("0 songs")