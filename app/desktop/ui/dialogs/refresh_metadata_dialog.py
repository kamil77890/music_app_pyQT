"""
Dialog for refreshing metadata by re-downloading songs from YouTube
"""

import os
from typing import List, Dict
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QMessageBox, QFrame, QProgressDialog, QCheckBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from app.desktop.config import config
from app.desktop.threads.refresh_metadata_thread import RefreshMetadataThread


class RefreshMetadataDialog(QDialog):
    """Dialog to refresh metadata by re-downloading songs (replaces broken files)"""

    def __init__(self, songs_data: List[Dict], playlist_folder: str = None, parent=None, refresh_all_mode: bool = False):
        super().__init__(parent)
        self.songs_data = songs_data
        self.playlist_folder = playlist_folder
        self.refresh_all_mode = refresh_all_mode
        self.setWindowTitle("🔄 Refresh All Songs" if refresh_all_mode else "🔄 Refresh Metadata (Re-download)")
        self.setFixedSize(820, 680)
        self.refresh_thread = None
        self.progress_dialog = None
        self.setup_ui()

    def setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        # Title with warning
        title = QLabel("🔄 Refresh All Songs" if self.refresh_all_mode else "🔄 Refresh Metadata (Re-download)")
        title.setProperty("title", True)
        title.setStyleSheet("font-size:18px;font-weight:700;")
        root.addWidget(title)

        if self.refresh_all_mode:
            warning = QLabel(
                "⚠️ This will DELETE and re-download ALL songs in your library!\n"
                f"Total songs to refresh: {len(self.songs_data)}\n\n"
                "Only use this when many songs have corrupted metadata."
            )
            warning.setStyleSheet("color:#ff6b6b;font-size:13px;font-weight:600;")
            warning.setWordWrap(True)
            root.addWidget(warning)
        else:
            warning = QLabel(
                "⚠️ This will DELETE broken files and download them again from YouTube.\n"
                "Only use this when metadata fixes don't work."
            )
            warning.setStyleSheet("color:#ff6b6b;font-size:13px;font-weight:500;")
            warning.setWordWrap(True)
            root.addWidget(warning)

        subtitle = QLabel(f"Found {len(self.songs_data)} file(s) to refresh.")
        subtitle.setStyleSheet("color:#8a9ba8;")
        root.addWidget(subtitle)

        # Song list (read-only, no selection)
        if self.refresh_all_mode:
            list_label = QLabel(f"📚 ALL songs in library ({len(self.songs_data)} total):")
            list_label.setStyleSheet("font-weight:700;color:#ffa94d;")
        else:
            list_label = QLabel("Files to refresh:")
            list_label.setStyleSheet("font-weight:600;")
        root.addWidget(list_label)

        self.songs_list = QListWidget()
        self.songs_list.setSelectionMode(QListWidget.NoSelection)

        for sd in self.songs_data:
            fp = sd.get("file_path") or sd.get("path", "")
            md = sd.get("metadata", {})
            title_txt = md.get("title") or os.path.splitext(os.path.basename(fp))[0]
            artist_txt = md.get("artist") or "Unknown Artist"

            issues = []
            if not md.get("artist") or md.get("artist") == "Unknown Artist":
                issues.append("❌ Missing artist")
            if not md.get("has_cover"):
                issues.append("❌ No cover")
            elif md.get("cover_size", 0) < 1024:
                issues.append("⚠️ Small cover")
            if not md.get("title") or md.get("title").startswith("Unknown"):
                issues.append("❌ Bad title")

            item_text = f"{title_txt} — {artist_txt}"
            if issues:
                item_text += f"\n    {' | '.join(issues)}"

            item = QListWidgetItem(item_text)
            item.setToolTip(fp)

            # Color code
            if "❌" in item_text:
                item.setForeground(QColor("#ff6b6b"))
            elif "⚠️" in item_text:
                item.setForeground(QColor("#ffa94d"))

            self.songs_list.addItem(item)

        root.addWidget(self.songs_list, 1)

        # Warning checkbox
        self.confirm_cb = QCheckBox("I understand this will delete and re-download these files")
        self.confirm_cb.setChecked(False)
        self.confirm_cb.setStyleSheet("font-weight:600;")
        root.addWidget(self.confirm_cb)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_btn)

        self.refresh_btn = QPushButton("🔄 Refresh & Re-download")
        self.refresh_btn.setProperty("primary", True)
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.clicked.connect(self.start_refresh)
        self.confirm_cb.toggled.connect(self.refresh_btn.setEnabled)
        btn_row.addWidget(self.refresh_btn)

        root.addLayout(btn_row)

    def start_refresh(self):
        if not self.confirm_cb.isChecked():
            QMessageBox.warning(self, "Confirmation Required",
                                "Please confirm that you understand this will delete files.")
            return

        # Close this dialog and show progress
        self.accept()

        # Show progress dialog
        self.progress_dialog = QProgressDialog(
            "Refreshing metadata...", "Cancel", 0, len(self.songs_data), self)
        self.progress_dialog.setWindowTitle("Refreshing Metadata")
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.canceled.connect(
            lambda: self.refresh_thread.stop() if self.refresh_thread else None)

        # Start thread
        download_path = config.get_download_path()
        self.refresh_thread = RefreshMetadataThread(
            self.songs_data, download_path, playlist_folder=self.playlist_folder)
        self.refresh_thread.progress.connect(self.on_progress)
        self.refresh_thread.complete.connect(self.on_complete)
        self.refresh_thread.error.connect(self.on_error)
        self.refresh_thread.start()
        self.progress_dialog.show()

    def on_progress(self, current: int, total: int, status: str):
        if self.progress_dialog:
            self.progress_dialog.setValue(current)
            self.progress_dialog.setLabelText(status)

    def on_complete(self, results: dict):
        if self.progress_dialog:
            self.progress_dialog.close()

        refreshed = results.get("refreshed", 0)
        failed = results.get("failed", 0)
        skipped = results.get("skipped", 0)

        # Build details message
        details = []
        for d in results.get("details", []):
            status_icon = "✅" if d["status"] == "Refreshed" else "❌" if d["status"] == "Failed" else "⚠️"
            details.append(f"{status_icon} {d['file']}: {d['status']}")
            if d.get("reason"):
                details.append(f"   Reason: {d['reason']}")

        msg = f"Refreshed: {refreshed}\nFailed: {failed}\nSkipped: {skipped}"
        if details:
            msg += "\n\nDetails:\n" + "\n".join(details[:20])  # Limit to first 20
            if len(details) > 20:
                msg += f"\n... and {len(details) - 20} more"

        if failed == 0:
            QMessageBox.information(self, "Refresh Complete", msg)
        else:
            QMessageBox.warning(self, "Refresh Complete (with errors)", msg)

    def on_error(self, error_msg: str):
        if self.progress_dialog:
            self.progress_dialog.close()
        QMessageBox.critical(self, "Error", f"An error occurred: {error_msg}")
