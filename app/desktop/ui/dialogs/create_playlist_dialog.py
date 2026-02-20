"""
Dialog for creating new playlists (modern layout)
"""

import os
import shutil
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QMessageBox, QFrame
)
from PyQt5.QtCore import Qt
from app.desktop.config import config
from app.desktop.utils.helpers import get_mp3_files_recursive
from app.desktop.utils.metadata import get_mp3_metadata


class CreatePlaylistDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create New Playlist")
        self.setFixedSize(720, 620)
        self.setup_ui()
        self.load_songs()

    def setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        title = QLabel("🎵 Create New Playlist")
        title.setProperty("title", True)
        title.setStyleSheet("font-size:18px;font-weight:700;")
        root.addWidget(title)

        # Name field
        name_frame = QFrame()
        name_layout = QHBoxLayout(name_frame)
        name_layout.setContentsMargins(0, 0, 0, 0)
        name_label = QLabel("Playlist name:")
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter playlist folder name")
        name_layout.addWidget(name_label)
        name_layout.addWidget(self.name_input)
        root.addWidget(name_frame)

        # List header
        header = QFrame()
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.addWidget(QLabel("Select songs to include"))
        h_layout.addStretch()
        self.selected_count = QLabel("0 selected")
        h_layout.addWidget(self.selected_count)
        root.addWidget(header)

        # Songs list
        self.songs_list = QListWidget()
        self.songs_list.setSelectionMode(QListWidget.MultiSelection)
        self.songs_list.itemSelectionChanged.connect(self.update_selected_count)
        root.addWidget(self.songs_list, 1)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(self.songs_list.selectAll)
        btn_row.addWidget(self.select_all_btn)

        self.deselect_btn = QPushButton("Deselect")
        self.deselect_btn.clicked.connect(self.songs_list.clearSelection)
        btn_row.addWidget(self.deselect_btn)

        self.create_btn = QPushButton("Create Playlist")
        self.create_btn.setProperty("primary", True)
        self.create_btn.clicked.connect(self.create_playlist)
        btn_row.addWidget(self.create_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_btn)

        root.addLayout(btn_row)

    def load_songs(self):
        download_path = config.get_download_path()
        mp3_files = get_mp3_files_recursive(download_path)

        seen = set()
        for fp in mp3_files:
            try:
                md = get_mp3_metadata(fp)
                title = md.get("title", os.path.basename(fp).replace(".mp3", ""))
                artist = md.get("artist", "Unknown Artist")
                key = f"{title}_{artist}".lower().strip()
                if key in seen:
                    continue
                seen.add(key)
                item = QListWidgetItem(f"{title} — {artist}")
                item.setData(Qt.UserRole, fp)
                item.setToolTip(fp)
                self.songs_list.addItem(item)
            except Exception:
                continue

    def update_selected_count(self):
        n = len(self.songs_list.selectedItems())
        self.selected_count.setText(f"{n} selected")

    def create_playlist(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing name", "Please enter a playlist name.")
            return

        items = self.songs_list.selectedItems()
        if not items:
            QMessageBox.warning(self, "No songs", "Please select at least one song.")
            return

        download_path = config.get_download_path()
        playlist_dir = os.path.join(download_path, name)

        if os.path.exists(playlist_dir):
            resp = QMessageBox.question(self, "Folder exists",
                                        f"Folder {name} exists. Overwrite?", QMessageBox.Yes | QMessageBox.No)
            if resp == QMessageBox.No:
                return
            shutil.rmtree(playlist_dir, ignore_errors=True)

        try:
            os.makedirs(playlist_dir, exist_ok=True)
            for it in items:
                src = it.data(Qt.UserRole)
                dst = os.path.join(playlist_dir, os.path.basename(src))
                shutil.copy2(src, dst)
            QMessageBox.information(self, "Created", f"Playlist '{name}' created with {len(items)} songs.")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create playlist:\n{str(e)}")
