"""
Dialog for fixing song metadata (modern UI)
"""

import os
from typing import List, Dict
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QMessageBox, QFrame, QWidget, QProgressDialog, QCheckBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from app.desktop.utils.metadata import get_mp3_metadata
from app.desktop.threads.fix_metadata_thread import FixMetadataThread


class FixMetadataDialog(QDialog):
    """Dialog to inspect and fix multiple files' metadata"""

    def __init__(self, songs_data: List[Dict], parent=None):
        super().__init__(parent)
        self.songs_data = songs_data
        self.setWindowTitle("🔧 Fix Song Metadata")
        self.setFixedSize(820, 680)
        self.fix_thread = None
        self.progress_dialog = None
        self.setup_ui()

    def setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        title = QLabel("🔧 Fix Song Metadata")
        title.setProperty("title", True)
        title.setStyleSheet("font-size:18px;font-weight:700;")
        root.addWidget(title)

        subtitle = QLabel(f"Found {len(self.songs_data)} file(s) that might need fixes.")
        subtitle.setStyleSheet("color:#8a9ba8;")
        root.addWidget(subtitle)

        # Selection header and list
        header_frame = QFrame()
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        sel_label = QLabel("Select songs to fix")
        header_layout.addWidget(sel_label)
        header_layout.addStretch()

        self.selected_count = QLabel("0 selected")
        header_layout.addWidget(self.selected_count)
        root.addWidget(header_frame)

        # Song list
        self.songs_list = QListWidget()
        self.songs_list.setSelectionMode(QListWidget.MultiSelection)

        # Update the song list item creation in FixMetadataDialog.setup_ui()
        for sd in self.songs_data:
            fp = sd.get("file_path")
            md = sd.get("metadata", {})
            title_txt = md.get("title") or os.path.basename(fp)
            artist_txt = md.get("artist") or "Unknown Artist"
            format = md.get("format", "unknown").upper()
            
            issues = []
            if not md.get("artist") or md.get("artist") == "Unknown Artist":
                issues.append("❌ Missing artist")
            if not md.get("has_cover"):
                issues.append("❌ No cover")
            elif md.get("cover_size", 0) < 1024:
                issues.append("⚠️ Small cover")
            if not md.get("title") or md.get("title").startswith("Unknown"):
                issues.append("❌ Bad title")
            
            item_text = f"[{format}] {title_txt} — {artist_txt}"
            if issues:
                item_text += f"\n    {' | '.join(issues)}"
            
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, sd)
            item.setToolTip(fp)
            item.setFlags(item.flags() | Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            
            # Color code based on severity
            if "❌" in item_text:
                item.setForeground(QColor("#ff6b6b"))  # Red for critical issues
            elif "⚠️" in item_text:
                item.setForeground(QColor("#ffa94d"))  # Orange for warnings
            
            self.songs_list.addItem(item)

        self.songs_list.itemSelectionChanged.connect(self.update_selected_count)
        root.addWidget(self.songs_list, 1)

        # Options
        opts_frame = QFrame()
        opts_layout = QHBoxLayout(opts_frame)
        opts_layout.setContentsMargins(0, 0, 0, 0)

        self.fetch_covers = QCheckBox("Fetch & embed cover from YouTube")
        self.fetch_covers.setChecked(True)
        self.overwrite = QCheckBox("Overwrite existing metadata")
        self.overwrite.setChecked(False)

        opts_layout.addWidget(self.fetch_covers)
        opts_layout.addWidget(self.overwrite)
        opts_layout.addStretch()
        root.addWidget(opts_frame)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(self.select_all)
        btn_row.addWidget(self.select_all_btn)

        self.deselect_all_btn = QPushButton("Deselect All")
        self.deselect_all_btn.clicked.connect(self.deselect_all)
        btn_row.addWidget(self.deselect_all_btn)

        self.fix_btn = QPushButton("Fix Selected")
        self.fix_btn.setProperty("primary", True)
        self.fix_btn.clicked.connect(self.fix_selected)
        btn_row.addWidget(self.fix_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_btn)

        root.addLayout(btn_row)

        self.update_selected_count()

    # --- Helpers ---

    def update_selected_count(self):
        n = len(self.songs_list.selectedItems())
        self.selected_count.setText(f"{n} selected")

    def select_all(self):
        self.songs_list.selectAll()
        self.update_selected_count()

    def deselect_all(self):
        self.songs_list.clearSelection()
        self.update_selected_count()

    # --- Fixing flow ---

    def fix_selected(self):
        items = self.songs_list.selectedItems()
        if not items:
            QMessageBox.warning(self, "No selection", "Please select at least one song to fix.")
            return

        to_fix = []
        for it in items:
            sd = it.data(Qt.UserRole)
            to_fix.append({
                "file_path": sd.get("file_path"),
                "metadata": sd.get("metadata"),
                "fetch_covers": self.fetch_covers.isChecked(),
                "overwrite": self.overwrite.isChecked()
            })

        # Start background thread
        self.fix_thread = FixMetadataThread(to_fix)
        self.fix_thread.progress.connect(self.on_progress)
        self.fix_thread.complete.connect(self.on_complete)  
        self.fix_thread.error.connect(self.on_error)

        # Modal progress dialog (native) to show progress
        self.progress_dialog = QProgressDialog("Fixing metadata...", "Cancel", 0, len(to_fix), self)
        self.progress_dialog.setWindowTitle("Fixing Metadata")
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.canceled.connect(lambda: self.fix_thread.stop() if hasattr(self.fix_thread, "stop") else None)
        self.fix_thread.start()
        self.progress_dialog.show()

    def on_progress(self, current: int, total: int, title: str):
        if self.progress_dialog:
            self.progress_dialog.setValue(current)
            self.progress_dialog.setLabelText(f"Fixing: {title} ({current}/{total})")

    def on_complete(self, results: list):
        if self.progress_dialog:
            self.progress_dialog.close()

        successful = sum(1 for r in results if r.get("success"))
        failed = len(results) - successful

        if failed == 0:
            QMessageBox.information(self, "Success", f"Fixed metadata for {successful} file(s).")
            self.accept()
        else:
            QMessageBox.warning(self, "Partial Success",
                                f"Fixed {successful} files. Failed to fix {failed} files. See logs.")
            self.accept()

    def on_error(self, error_msg: str):
        if self.progress_dialog:
            self.progress_dialog.close()
        QMessageBox.critical(self, "Error", f"An error occurred: {error_msg}")
