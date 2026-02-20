"""
Playlist tree widget with context menu
"""

import os
from PyQt5.QtWidgets import (
    QTreeWidget, QTreeWidgetItem, QMenu, QInputDialog,
    QFileDialog, QMessageBox, QAction
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from app.desktop.config import config
from app.desktop.utils.metadata import get_mp3_metadata
import shutil
import sys


class PlaylistTreeWidget(QTreeWidget):
    
    folder_selected = pyqtSignal(str)
    song_double_clicked = pyqtSignal(str, dict)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.refresh()
    
    def setup_ui(self):
        """Setup the UI elements"""
        self.setHeaderHidden(True)
        self.setColumnCount(2)
        self.setColumnHidden(1, True)  # Hide path column
        
        # Context menu
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        
        # Connect signals
        self.itemDoubleClicked.connect(self.on_item_double_clicked)
    
    def refresh(self):
        """Refresh the tree view"""
        self.clear()
        
        download_path = config.get_download_path()
        
        # Create root item
        root_item = QTreeWidgetItem(self, ["📁 Music Library", download_path])
        root_item.setData(0, Qt.UserRole, download_path)
        root_item.setFont(0, QFont("Segoe UI", 11, QFont.Bold))
        
        # Add all items
        self.add_folder_items(root_item, download_path)
        
        # Expand root
        root_item.setExpanded(True)
        
        self.resizeColumnToContents(0)
    
    def add_folder_items(self, parent_item, folder_path):
        """Add folders and songs to the tree"""
        try:
            if not os.path.exists(folder_path):
                return
            
            # Get all items in folder
            items = os.listdir(folder_path)
            
            # Sort: folders first, then files
            folders = []
            files = []
            
            for item in items:
                item_path = os.path.join(folder_path, item)
                if os.path.isdir(item_path):
                    folders.append(item)
                elif item.lower().endswith('.mp3'):
                    files.append(item)
            
            # Add folders
            for folder in sorted(folders):
                folder_path_full = os.path.join(folder_path, folder)
                folder_item = QTreeWidgetItem(parent_item, [f"📁 {folder}", folder_path_full])
                folder_item.setData(0, Qt.UserRole, folder_path_full)
                
                # Recursively add subfolders
                self.add_folder_items(folder_item, folder_path_full)
            
            # Add songs
            for file in sorted(files):
                file_path = os.path.join(folder_path, file)
                metadata = get_mp3_metadata(file_path)
                title = metadata.get('title', os.path.splitext(file)[0])
                
                song_item = QTreeWidgetItem(parent_item, [f"🎵 {title}", file_path])
                song_item.setData(0, Qt.UserRole, file_path)
                song_item.setData(0, Qt.UserRole + 1, metadata)
        except Exception as e:
            print(f"Error loading folder {folder_path}: {e}")
    
    def on_item_double_clicked(self, item, column):
        """Handle item double click"""
        item_path = item.data(0, Qt.UserRole)
        
        if os.path.isfile(item_path):
            # It's a song - emit signal
            metadata = item.data(0, Qt.UserRole + 1) or {}
            self.song_double_clicked.emit(item_path, metadata)
        else:
            # It's a folder - toggle expansion
            item.setExpanded(not item.isExpanded())
            self.folder_selected.emit(item_path)
    
    def show_context_menu(self, position):
        """Show context menu for tree items"""
        item = self.itemAt(position)
        
        menu = QMenu()
        
        if item is None:
            # Root level actions
            menu.addAction("📁 Create New Playlist", self.create_playlist)
            menu.addAction("🔄 Refresh", self.refresh)
            menu.addAction("📂 Open Library Folder", self.open_library_folder)
        elif os.path.isfile(item.data(0, Qt.UserRole)):
            # Song actions
            menu.addAction("▶ Play", lambda: self.play_song(item))
            menu.addAction("📂 Show in Folder", lambda: self.show_in_folder(item))
            menu.addSeparator()
            menu.addAction("🗑️ Delete Song", lambda: self.delete_item(item))
        else:
            # Folder actions
            menu.addAction("📁 Create Sub-Playlist", lambda: self.create_sub_playlist(item))
            menu.addAction("✏️ Rename Playlist", lambda: self.rename_item(item))
            menu.addSeparator()
            menu.addAction("📂 Open Folder", lambda: self.open_folder(item))
            menu.addSeparator()
            menu.addAction("🗑️ Delete Playlist", lambda: self.delete_item(item))
        
        menu.exec_(self.viewport().mapToGlobal(position))
    
    def create_playlist(self):
        """Create a new playlist (folder)"""
        from app.desktop.ui.dialogs.create_playlist_dialog import CreatePlaylistDialog
        dialog = CreatePlaylistDialog(self.parent())
        if dialog.exec_():
            self.refresh()
    
    def create_sub_playlist(self, parent_item):
        """Create a sub-playlist"""
        parent_path = parent_item.data(0, Qt.UserRole)
        
        name, ok = QInputDialog.getText(
            self, "Create Sub-Playlist",
            "Enter sub-playlist name:",
            text="New Sub-Playlist"
        )
        
        if ok and name:
            new_folder = os.path.join(parent_path, name)
            
            try:
                os.makedirs(new_folder, exist_ok=True)
                self.refresh()
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not create sub-playlist: {e}")
    
    def rename_item(self, item):
        """Rename a folder"""
        old_path = item.data(0, Qt.UserRole)
        old_name = os.path.basename(old_path)
        
        new_name, ok = QInputDialog.getText(
            self, "Rename Playlist",
            "Enter new playlist name:",
            text=old_name
        )
        
        if ok and new_name and new_name != old_name:
            new_path = os.path.join(os.path.dirname(old_path), new_name)
            
            try:
                os.rename(old_path, new_path)
                self.refresh()
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not rename playlist: {e}")
    
    def delete_item(self, item):
        """Delete a folder or file"""
        path = item.data(0, Qt.UserRole)
        is_file = os.path.isfile(path)
        
        item_type = "song" if is_file else "playlist"
        confirm_text = f"Are you sure you want to delete this {item_type}?"
        if not is_file:
            confirm_text += "\n\nWarning: This will delete the entire folder and all its contents!"
        
        reply = QMessageBox.question(
            self, "Delete",
            confirm_text,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                if is_file:
                    os.remove(path)
                else:
                    shutil.rmtree(path)
                self.refresh()
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not delete: {e}")
    
    def play_song(self, item):
        """Play the selected song"""
        path = item.data(0, Qt.UserRole)
        metadata = item.data(0, Qt.UserRole + 1) or {}
        self.song_double_clicked.emit(path, metadata)
    
    def show_in_folder(self, item):
        """Show the song in file explorer"""
        path = item.data(0, Qt.UserRole)
        if os.path.exists(path):
            import subprocess
            if sys.platform == "win32":
                os.startfile(os.path.dirname(path))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", os.path.dirname(path)])
            else:
                subprocess.Popen(["xdg-open", os.path.dirname(path)])
    
    def open_folder(self, item):
        """Open the folder in file explorer"""
        path = item.data(0, Qt.UserRole)
        if os.path.exists(path):
            import subprocess
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
    
    def open_library_folder(self):
        """Open the library folder"""
        download_path = config.get_download_path()
        if os.path.exists(download_path):
            import subprocess
            if sys.platform == "win32":
                os.startfile(download_path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", download_path])
            else:
                subprocess.Popen(["xdg-open", download_path])