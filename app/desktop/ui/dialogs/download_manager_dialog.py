"""
DownloadManagerDialog
─────────────────────
Full-featured download popup that wraps the real DownloadThread.

Features
--------
• Per-song row with title, artist, progress bar, status icon, Remove button
• Overall progress bar
• Pause / Resume the whole queue
• Cancel All
• "Create playlist from downloaded songs" toggle + name field
• Non-modal — user can keep browsing while downloading

Signals
-------
download_finished(playlist_name: str)
    playlist_name is "" if the user didn't want to create one.

Placement
---------
app/desktop/ui/dialogs/download_manager_dialog.py
"""

from __future__ import annotations

import os
import shutil
from typing import List, Dict, Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QScrollArea, QFrame, QWidget, QLineEdit,
    QCheckBox, QSizePolicy, QMessageBox
)

from app.desktop.threads.download_thread import DownloadThread
from app.desktop.config import config


# ─────────────────────────────────────────────────────────────────
#  Song row widget
# ─────────────────────────────────────────────────────────────────
class _SongRow(QFrame):
    remove_clicked = pyqtSignal(int)

    WAITING  = "waiting"
    ACTIVE   = "active"
    DONE     = "done"
    FAILED   = "failed"
    REMOVED  = "removed"

    _ICONS = {
        WAITING : ("⏳", "#6e7080"),
        ACTIVE  : ("⟳",  "#4d59fb"),
        DONE    : ("✓",  "#22c55e"),
        FAILED  : ("✗",  "#ef4444"),
        REMOVED : ("—",  "#3a3a55"),
    }

    def __init__(self, index: int, title: str, artist: str, parent=None):
        super().__init__(parent)
        self._index  = index
        self._status = self.WAITING
        self.setFixedHeight(60)
        self.setStyleSheet(
            "QFrame{background:#111118;border-radius:10px;border:1px solid #1e1e38;}")
        self._build(title, artist)

    def _build(self, title: str, artist: str):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(10)

        self._icon = QLabel("⏳")
        self._icon.setFixedWidth(22)
        self._icon.setStyleSheet(
            "color:#6e7080;font-size:14px;background:transparent;")
        lay.addWidget(self._icon)

        meta = QWidget()
        meta.setStyleSheet("background:transparent;")
        ml = QVBoxLayout(meta)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(2)

        self._title_lbl = QLabel(title[:55] + "…" if len(title) > 55 else title)
        self._title_lbl.setStyleSheet(
            "color:#e8eaf0;font-size:12px;font-weight:700;background:transparent;")
        ml.addWidget(self._title_lbl)

        self._artist_lbl = QLabel(artist[:45] + "…" if len(artist) > 45 else artist)
        self._artist_lbl.setStyleSheet(
            "color:#6e7080;font-size:10px;background:transparent;")
        ml.addWidget(self._artist_lbl)

        lay.addWidget(meta, 1)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setFixedWidth(120)
        self._bar.setFixedHeight(6)
        self._bar.setTextVisible(False)
        self._bar.setStyleSheet("""
            QProgressBar{background:#1e1e38;border:none;border-radius:3px;}
            QProgressBar::chunk{background:#4d59fb;border-radius:3px;}
        """)
        lay.addWidget(self._bar)

        self._remove_btn = QPushButton("✕")
        self._remove_btn.setFixedSize(26, 26)
        self._remove_btn.setToolTip("Remove from queue")
        self._remove_btn.setStyleSheet("""
            QPushButton{background:#1e1e38;border:none;border-radius:13px;
                        color:#6e7080;font-size:11px;}
            QPushButton:hover{background:#ef4444;color:#fff;}
        """)
        self._remove_btn.clicked.connect(
            lambda: self.remove_clicked.emit(self._index))
        lay.addWidget(self._remove_btn)

    # ── public ─────────────────────────────────────────────────

    def set_progress(self, pct: int):
        self._bar.setValue(pct)

    def set_status(self, status: str):
        self._status = status
        icon, color = self._ICONS.get(status, ("?", "#fff"))
        self._icon.setText(icon)
        self._icon.setStyleSheet(
            f"color:{color};font-size:14px;background:transparent;")

        if status == self.DONE:
            self._bar.setValue(100)
            self._bar.setStyleSheet("""
                QProgressBar{background:#1e1e38;border:none;border-radius:3px;}
                QProgressBar::chunk{background:#22c55e;border-radius:3px;}
            """)
            self._remove_btn.setEnabled(False)

        elif status == self.FAILED:
            self._bar.setStyleSheet("""
                QProgressBar{background:#1e1e38;border:none;border-radius:3px;}
                QProgressBar::chunk{background:#ef4444;border-radius:3px;}
            """)

        elif status == self.ACTIVE:
            self.setStyleSheet(
                "QFrame{background:#141430;border-radius:10px;border:1px solid #4d59fb;}")

        elif status == self.REMOVED:
            self.setStyleSheet(
                "QFrame{background:#0d0d18;border-radius:10px;border:1px solid #1e1e38;}")
            self._title_lbl.setStyleSheet(
                "color:#3a3a55;font-size:12px;font-weight:700;background:transparent;")
            self._remove_btn.setEnabled(False)

        if status == self.WAITING:
            self._remove_btn.setEnabled(True)


# ─────────────────────────────────────────────────────────────────
#  Dialog
# ─────────────────────────────────────────────────────────────────
class DownloadManagerDialog(QDialog):
    """Non-modal download manager that wraps the real DownloadThread."""

    download_finished = pyqtSignal(str)   # playlist_name or ""

    def __init__(
        self,
        songs: List[Dict],
        download_path: str,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Download Manager")
        self.setMinimumSize(640, 580)
        self.setModal(False)

        self._songs         = [dict(s) for s in songs]
        self._download_path = download_path
        self._thread: Optional[DownloadThread] = None
        self._rows: List[_SongRow] = []
        self._done_count    = 0
        self._total         = len(songs)
        self._paused        = False
        self._finished      = False
        self._downloaded_paths: List[str] = []

        # tracks which list-index is "current" (matched by order, not title)
        self._current_index = -1

        self._build_ui()
        self._start()

    # ── build ──────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        # title
        title = QLabel("⬇  Download Manager")
        title.setStyleSheet(
            "color:#ffffff;font-size:18px;font-weight:800;background:transparent;")
        root.addWidget(title)

        # overall bar
        self._overall_bar = QProgressBar()
        self._overall_bar.setRange(0, max(self._total, 1))
        self._overall_bar.setValue(0)
        self._overall_bar.setFixedHeight(10)
        self._overall_bar.setTextVisible(False)
        self._overall_bar.setStyleSheet("""
            QProgressBar{background:#1e1e38;border:none;border-radius:5px;}
            QProgressBar::chunk{
                background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #4d59fb,stop:1 #6c3aef);
                border-radius:5px;}
        """)
        root.addWidget(self._overall_bar)

        self._status_lbl = QLabel(f"0 / {self._total} completed")
        self._status_lbl.setStyleSheet(
            "color:#6e7080;font-size:12px;background:transparent;")
        root.addWidget(self._status_lbl)

        # rows scroll
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background:transparent;border:none;")

        rows_w = QWidget()
        rows_w.setStyleSheet("background:transparent;")
        self._rows_lay = QVBoxLayout(rows_w)
        self._rows_lay.setContentsMargins(0, 0, 0, 0)
        self._rows_lay.setSpacing(6)

        for i, s in enumerate(self._songs):
            row = _SongRow(
                index  = i,
                title  = s.get("title",  f"Track {i+1}"),
                artist = s.get("artist", "Unknown Artist"),
            )
            row.remove_clicked.connect(self._remove_song)
            self._rows_lay.addWidget(row)
            self._rows.append(row)

        self._rows_lay.addStretch()
        scroll.setWidget(rows_w)
        root.addWidget(scroll, 1)

        # playlist option
        pl_frame = QFrame()
        pl_frame.setStyleSheet(
            "background:#111118;border:1px solid #1e1e38;border-radius:12px;")
        pl_lay = QVBoxLayout(pl_frame)
        pl_lay.setContentsMargins(14, 10, 14, 10)
        pl_lay.setSpacing(8)

        self._pl_check = QCheckBox(
            "Create playlist from downloaded songs")
        self._pl_check.setStyleSheet(
            "color:#e8eaf0;font-size:13px;font-weight:600;")
        self._pl_check.stateChanged.connect(self._toggle_pl_name)
        pl_lay.addWidget(self._pl_check)

        self._pl_name = QLineEdit()
        self._pl_name.setPlaceholderText("Playlist name…")
        self._pl_name.setFixedHeight(36)
        self._pl_name.setVisible(False)
        self._pl_name.setStyleSheet("""
            QLineEdit{background:#0d0d18;border:1px solid #2a2a50;
                      border-radius:8px;color:#e8eaf0;
                      font-size:13px;padding:0 10px;}
            QLineEdit:focus{border-color:#4d59fb;}
        """)
        pl_lay.addWidget(self._pl_name)
        root.addWidget(pl_frame)

        # buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self._pause_btn = QPushButton("⏸  Pause")
        self._pause_btn.setFixedHeight(38)
        self._pause_btn.setStyleSheet("""
            QPushButton{background:#1e1e38;border:1px solid #2a2a50;
                        border-radius:10px;color:#e8eaf0;font-weight:700;
                        font-size:13px;padding:0 16px;}
            QPushButton:hover{background:#2a2a50;}
            QPushButton:disabled{color:#3a3a55;}
        """)
        self._pause_btn.clicked.connect(self._toggle_pause)
        btn_row.addWidget(self._pause_btn)

        btn_row.addStretch()

        self._cancel_btn = QPushButton("✕  Cancel All")
        self._cancel_btn.setFixedHeight(38)
        self._cancel_btn.setStyleSheet("""
            QPushButton{background:#1e1e38;border:1px solid #ef4444;
                        border-radius:10px;color:#ef4444;font-weight:700;
                        font-size:13px;padding:0 16px;}
            QPushButton:hover{background:#ef4444;color:#fff;}
        """)
        self._cancel_btn.clicked.connect(self._cancel_all)
        btn_row.addWidget(self._cancel_btn)

        self._close_btn = QPushButton("✓  Done")
        self._close_btn.setFixedHeight(38)
        self._close_btn.setEnabled(False)
        self._close_btn.setStyleSheet("""
            QPushButton{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,
                            stop:0 #4d59fb,stop:1 #6c3aef);
                        border:none;border-radius:10px;color:#fff;
                        font-weight:700;font-size:13px;padding:0 22px;}
            QPushButton:disabled{background:#1e1e38;color:#3a3a55;}
            QPushButton:hover{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,
                            stop:0 #5e6aff,stop:1 #7a4aff);}
        """)
        self._close_btn.clicked.connect(self._on_close)
        btn_row.addWidget(self._close_btn)

        root.addLayout(btn_row)

    # ── start ──────────────────────────────────────────────────

    def _start(self):
        self._thread = DownloadThread(self._songs, self._download_path)

        # progress(percent, title, current, total)
        self._thread.progress.connect(self._on_progress)
        # song_complete(song_dict, success, file_path, error_msg)
        self._thread.song_complete.connect(self._on_song_complete)
        # finished(downloaded_paths)
        self._thread.finished.connect(self._on_all_done)

        self._thread.start()

    # ── thread slots ───────────────────────────────────────────

    def _on_progress(self, percent: int, title: str, current: int, total: int):
        """Called by DownloadThread.progress — marks the current song active."""
        # current is 1-based
        idx = current - 1
        if self._current_index != idx:
            self._current_index = idx
            if 0 <= idx < len(self._rows):
                self._rows[idx].set_status(_SongRow.ACTIVE)
            self._status_lbl.setText(
                f"Downloading: {title[:50]}…  ({current}/{total})")

        if 0 <= idx < len(self._rows):
            self._rows[idx].set_progress(percent)

    def _on_song_complete(
        self,
        song_dict: dict,
        success: bool,
        file_path: str,
        error_msg: str,
    ):
        self._done_count += 1
        self._overall_bar.setValue(self._done_count)

        # find the matching row by position (current_index already advanced)
        idx = self._current_index
        if 0 <= idx < len(self._rows):
            status = _SongRow.DONE if success else _SongRow.FAILED
            self._rows[idx].set_status(status)

        if success and file_path:
            self._downloaded_paths.append(file_path)

        self._status_lbl.setText(
            f"{self._done_count} / {self._total} completed")

    def _on_all_done(self, downloaded: list):
        self._finished = True
        ok = len(downloaded)
        fail = self._total - self._done_count
        self._status_lbl.setText(
            f"✓ Done — {ok} downloaded, {fail} failed")
        self._pause_btn.setEnabled(False)
        self._cancel_btn.setEnabled(False)
        self._close_btn.setEnabled(True)

    # ── controls ───────────────────────────────────────────────

    def _remove_song(self, index: int):
        if self._thread:
            self._thread.remove_song(index)
        if 0 <= index < len(self._rows):
            self._rows[index].set_status(_SongRow.REMOVED)
        self._total = max(0, self._total - 1)
        self._overall_bar.setMaximum(max(self._total, 1))

    def _toggle_pause(self):
        if not self._thread:
            return
        self._paused = not self._paused
        if self._paused:
            self._thread.pause()
            self._pause_btn.setText("▶  Resume")
            self._status_lbl.setText("⏸ Paused — click Resume to continue")
        else:
            self._thread.resume()
            self._pause_btn.setText("⏸  Pause")

    def _cancel_all(self):
        reply = QMessageBox.question(
            self, "Cancel Downloads",
            "Cancel all remaining downloads?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            if self._thread:
                self._thread.stop()
            # _on_all_done will be called when thread finishes naturally;
            # force UI update immediately
            self._finished = True
            self._status_lbl.setText("✕ Downloads cancelled")
            self._pause_btn.setEnabled(False)
            self._cancel_btn.setEnabled(False)
            self._close_btn.setEnabled(True)

    def _toggle_pl_name(self, state):
        self._pl_name.setVisible(state == Qt.Checked)
        if state == Qt.Checked:
            self._pl_name.setFocus()

    def _on_close(self):
        playlist_name = ""
        if self._pl_check.isChecked():
            playlist_name = self._pl_name.text().strip()
            if not playlist_name:
                QMessageBox.warning(
                    self, "Playlist Name",
                    "Please enter a name for the playlist.")
                return
            self._create_playlist(playlist_name)

        self.download_finished.emit(playlist_name)
        self.accept()

    def _create_playlist(self, name: str):
        """Copy successfully downloaded files into a new playlist folder."""
        if not self._downloaded_paths:
            return
        folder = os.path.join(self._download_path, name)
        os.makedirs(folder, exist_ok=True)
        for fp in self._downloaded_paths:
            if os.path.isfile(fp):
                try:
                    shutil.copy2(fp, os.path.join(folder, os.path.basename(fp)))
                except Exception as exc:
                    print(f"[Playlist copy] {exc}")

    # ── close guard ────────────────────────────────────────────

    def closeEvent(self, event):
        if not self._finished:
            reply = QMessageBox.question(
                self, "Downloads in progress",
                "Downloads are still running. Cancel them and close?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply == QMessageBox.No:
                event.ignore()
                return
            if self._thread:
                self._thread.stop()
                self._thread.wait(2000)
        event.accept()