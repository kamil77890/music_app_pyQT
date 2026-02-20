"""
Progress dialog for showing download progress (modern MusicFlow layout)
"""

import os
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QProgressBar, QPushButton, QFrame, QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QIcon


class ProgressDialog(QDialog):
    """Dialog for showing download progress"""

    def __init__(self, total_songs: int, parent=None):
        super().__init__(parent)
        self.total_songs = total_songs
        self.current_song = 0
        self.setWindowTitle("Download Progress")
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint | Qt.MSWindowsFixedSizeDialogHint)
        self.setModal(True)
        self.setup_ui()

    def setup_ui(self):
        self.setFixedSize(480, 220)

        # Root layout
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        # Title block (hero-ish)
        title_frame = QFrame()
        title_layout = QHBoxLayout(title_frame)
        title_layout.setContentsMargins(8, 4, 8, 4)

        title_label = QLabel("📥 Downloading")
        title_label.setProperty("title", True)
        title_label.setStyleSheet("font-size:16px; font-weight:700;")
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        self.cancel_icon = QLabel()
        self.cancel_icon.setFixedSize(20, 20)
        title_layout.addWidget(self.cancel_icon)

        root.addWidget(title_frame)

        # Progress bar (large)
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedHeight(26)
        root.addWidget(self.progress_bar)

        # Current file & overall labels
        self.current_label = QLabel("Preparing downloads...")
        self.current_label.setWordWrap(True)
        self.current_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        root.addWidget(self.current_label)

        self.overall_label = QLabel(f"0 / {self.total_songs}")
        self.overall_label.setStyleSheet("color: #8a9ba8; font-size:12px;")
        root.addWidget(self.overall_label)

        # Buttons (minimize + cancel/close)
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.minimize_btn = QPushButton("Minimize")
        self.minimize_btn.setFixedHeight(32)
        self.minimize_btn.clicked.connect(self.on_minimize)
        btn_row.addWidget(self.minimize_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setFixedHeight(32)
        self.cancel_btn.clicked.connect(self.on_cancel)
        btn_row.addWidget(self.cancel_btn)

        root.addLayout(btn_row)


    def update_progress(self, value: int, song_title: str, current: int, total: int):
        """Update the progress display (called from DownloadThread.progress)."""
        self.progress_bar.setValue(int(value))
        self.current_label.setText(f"Downloading: {song_title}")
        self.overall_label.setText(f"{current} / {total}")
        self.current_song = current

    def complete(self):
        """Mark complete and auto-close after a short delay."""
        self.progress_bar.setValue(100)
        self.current_label.setText("✓ All downloads finished")
        self.overall_label.setText(f"Downloaded {self.current_song} of {self.total_songs}")
        self.cancel_btn.setText("Close")
        try:
            # reconnect close
            self.cancel_btn.clicked.disconnect()
        except Exception:
            pass
        self.cancel_btn.clicked.connect(self.accept)
        QTimer.singleShot(1800, self.accept)

    def set_error(self, error_message: str):
        """Show an error state."""
        self.current_label.setText(f"✗ Error: {error_message}")
        self.cancel_btn.setText("Close")
        try:
            self.cancel_btn.clicked.disconnect()
        except Exception:
            pass
        self.cancel_btn.clicked.connect(self.reject)


    def on_cancel(self):
        """User cancels: stop the download thread on parent if present."""
        parent = self.parent()
        if parent and hasattr(parent, "download_thread") and parent.download_thread:
            try:
                # stop thread gracefully if it supports terminate/stop
                if hasattr(parent.download_thread, "terminate"):
                    parent.download_thread.terminate()
                elif hasattr(parent.download_thread, "stop"):
                    parent.download_thread.stop()
            except Exception:
                pass
        self.reject()

    def on_minimize(self):
        """Minimize dialog to let user keep working."""
        self.showMinimized()
