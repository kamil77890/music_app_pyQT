"""
PlaybackController — right panel: album / playlist track list only.
Tracks are selectable (click to toggle). Download All downloads selected or all.
"""
from __future__ import annotations

from typing import List, Dict

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap, QPainter, QPainterPath, QColor, QFont, QLinearGradient
from PyQt5.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QSizePolicy,
)

from app.desktop.utils.helpers import clean_video_id
from app.desktop.threads.thumbnail_loader import ThumbnailLoader


class _BrowseTrackRow(QWidget):
    """Single track row with 44×44 cover thumbnail, selectable via click."""
    play_requested = pyqtSignal(dict)

    THUMB_SIZE = 44

    def __init__(self, index: int, track: dict, parent=None):
        super().__init__(parent)
        self._track = track
        self._selected = False
        self._loader = None
        self.setFixedHeight(56)
        self.setCursor(Qt.PointingHandCursor)

        self._normal_ss = (
            "background-color:#0f0f18;border:1px solid transparent;border-radius:10px;")
        self._selected_ss = (
            "background-color:#141428;border:1px solid #1DB954;border-radius:10px;")
        self.setStyleSheet(self._normal_ss)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 4, 10, 4)
        lay.setSpacing(8)

        idx_lbl = QLabel(str(index + 1))
        idx_lbl.setFixedWidth(20)
        idx_lbl.setAlignment(Qt.AlignCenter)
        idx_lbl.setStyleSheet("color:#4a4a65;font-size:10px;font-weight:700;background:transparent;")
        lay.addWidget(idx_lbl)

        self._thumb_lbl = QLabel()
        self._thumb_lbl.setFixedSize(self.THUMB_SIZE, self.THUMB_SIZE)
        self._thumb_lbl.setAlignment(Qt.AlignCenter)
        self._set_thumb_placeholder()
        lay.addWidget(self._thumb_lbl)

        thumb_url = (track.get("high_res_thumbnail") or track.get("thumbnail")
                     or track.get("cover") or "")
        if thumb_url and thumb_url.startswith("http"):
            self._start_thumb_load(thumb_url)

        meta = QWidget()
        meta.setStyleSheet("background:transparent;")
        ml = QVBoxLayout(meta)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(1)
        title_txt = track.get("title", f"Track {index + 1}")
        t_lbl = QLabel(title_txt)
        t_lbl.setStyleSheet("color:#e8eaf0;font-size:11px;font-weight:700;background:transparent;")
        t_lbl.setText(t_lbl.fontMetrics().elidedText(title_txt, Qt.ElideRight, 160))
        ml.addWidget(t_lbl)
        artist = track.get("artist", "")
        if artist:
            a_lbl = QLabel(artist)
            a_lbl.setStyleSheet("color:#5a5a72;font-size:9px;background:transparent;")
            a_lbl.setText(a_lbl.fontMetrics().elidedText(artist, Qt.ElideRight, 160))
            ml.addWidget(a_lbl)
        lay.addWidget(meta, 1)

        dur = track.get("duration", "")
        if dur:
            d_lbl = QLabel(str(dur))
            d_lbl.setStyleSheet("color:#3a3a55;font-size:9px;background:transparent;min-width:30px;")
            d_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            lay.addWidget(d_lbl)

    def _set_thumb_placeholder(self):
        s = self.THUMB_SIZE
        px = QPixmap(s, s)
        g = QLinearGradient(0, 0, s, s)
        g.setColorAt(0, QColor("#1a1a3a"))
        g.setColorAt(1, QColor("#0d0d20"))
        px.fill(QColor("#1a1a3a"))
        p = QPainter(px)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, s, s, 6, 6)
        p.setClipPath(path)
        p.fillRect(0, 0, s, s, g)
        p.setPen(QColor("#3a3a55"))
        p.setFont(QFont("Arial", 14, QFont.Bold))
        p.drawText(0, 0, s, s, Qt.AlignCenter, "♪")
        p.end()
        self._thumb_lbl.setPixmap(px)

    def _start_thumb_load(self, url: str):
        try:
            self._loader = ThumbnailLoader(url)
            self._loader.loaded.connect(self._on_thumb)
            self._loader.finished.connect(self._cleanup_loader)
            self._loader.start()
        except Exception:
            pass

    def _on_thumb(self, pixmap: QPixmap):
        if pixmap.isNull():
            return
        s = self.THUMB_SIZE
        scaled = pixmap.scaled(s, s, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        result = QPixmap(s, s)
        result.fill(Qt.transparent)
        p = QPainter(result)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, s, s, 6, 6)
        p.setClipPath(path)
        x = (scaled.width() - s) // 2
        y = (scaled.height() - s) // 2
        p.drawPixmap(-x, -y, scaled)
        p.end()
        self._thumb_lbl.setPixmap(result)

    def _cleanup_loader(self):
        if self._loader:
            try:
                self._loader.loaded.disconnect()
                self._loader.finished.disconnect()
            except Exception:
                pass
            self._loader = None

    def is_selected(self) -> bool:
        return self._selected

    def set_selected(self, sel: bool):
        self._selected = sel
        self.setStyleSheet(self._selected_ss if sel else self._normal_ss)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._selected = not self._selected
            self.setStyleSheet(self._selected_ss if self._selected else self._normal_ss)
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.play_requested.emit(self._track)
        super().mouseDoubleClickEvent(e)


class PlaybackController(QFrame):
    """Right column — album / playlist tracks only."""

    browse_track_play_requested = pyqtSignal(str, dict)
    browse_track_download_requested = pyqtSignal(dict)
    download_all_album_requested = pyqtSignal(list)
    album_panel_closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("album_panel")
        self.setStyleSheet("QFrame#album_panel{background:#000000;border:none;}")
        self.setFixedWidth(310)

        self._browse_tracks: List[Dict] = []
        self._browse_rows: List[_BrowseTrackRow] = []

        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._browse_top = QWidget()
        self._browse_top.setVisible(False)
        self._browse_top.setMinimumHeight(200)
        self._browse_top.setStyleSheet("background:transparent;")
        bt_lay = QVBoxLayout(self._browse_top)
        bt_lay.setContentsMargins(0, 0, 0, 0)
        bt_lay.setSpacing(0)
        self._browse_page = self._build_browse_section()
        bt_lay.addWidget(self._browse_page)
        root.addWidget(self._browse_top, 1)

    def _build_browse_section(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background:transparent;")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(14, 12, 14, 8)
        lay.setSpacing(0)

        hdr_row = QHBoxLayout()
        back_btn = QPushButton("← Close")
        back_btn.setStyleSheet(
            "QPushButton{background:transparent;border:none;color:#4d59fb;"
            "font-size:11px;font-weight:700;padding:0;text-align:left;"
            "min-height:24px;max-height:24px;}"
            "QPushButton:hover{color:#7a86ff;}")
        back_btn.setFixedHeight(24)
        back_btn.clicked.connect(self._on_close_album)
        hdr_row.addWidget(back_btn)
        hdr_row.addStretch()
        self._browse_mode_lbl = QLabel("ALBUM")
        self._browse_mode_lbl.setObjectName("np_label_small")
        hdr_row.addWidget(self._browse_mode_lbl)
        lay.addLayout(hdr_row)
        lay.addSpacing(8)

        self._browse_title_lbl = QLabel("")
        self._browse_title_lbl.setAlignment(Qt.AlignLeft)
        self._browse_title_lbl.setWordWrap(True)
        self._browse_title_lbl.setStyleSheet(
            "color:#ffffff;font-size:14px;font-weight:800;background:transparent;")
        lay.addWidget(self._browse_title_lbl)
        lay.addSpacing(2)

        self._browse_count_lbl = QLabel("")
        self._browse_count_lbl.setObjectName("np_artist_name")
        self._browse_count_lbl.setAlignment(Qt.AlignLeft)
        lay.addWidget(self._browse_count_lbl)
        lay.addSpacing(6)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        self._dl_all_browse_btn = QPushButton("⬇  Download All")
        self._dl_all_browse_btn.setFixedHeight(30)
        self._dl_all_browse_btn.setStyleSheet(
            "QPushButton{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #4d59fb,stop:1 #6c3aef);border:none;border-radius:8px;"
            "color:#fff;font-size:10px;font-weight:700;padding:0 12px;"
            "min-height:30px;max-height:30px;}"
            "QPushButton:hover{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #5e6aff,stop:1 #7a4aff);}")
        self._dl_all_browse_btn.clicked.connect(self._on_download_all_browse)
        btn_row.addWidget(self._dl_all_browse_btn)

        self._dl_sel_btn = QPushButton("⬇  Download Selected")
        self._dl_sel_btn.setFixedHeight(30)
        self._dl_sel_btn.setStyleSheet(
            "QPushButton{background:#1e1e38;border:1px solid #2e2e48;border-radius:8px;"
            "color:#9395a5;font-size:10px;font-weight:700;padding:0 10px;"
            "min-height:30px;max-height:30px;}"
            "QPushButton:hover{background:#2a2a44;color:#fff;}")
        self._dl_sel_btn.clicked.connect(self._on_download_selected)
        self._dl_sel_btn.setVisible(False)
        btn_row.addWidget(self._dl_sel_btn)
        btn_row.addStretch()
        lay.addLayout(btn_row)
        lay.addSpacing(6)

        self._browse_loading_lbl = QLabel("Loading tracks…")
        self._browse_loading_lbl.setObjectName("empty_state")
        self._browse_loading_lbl.setAlignment(Qt.AlignCenter)
        self._browse_loading_lbl.setVisible(False)
        lay.addWidget(self._browse_loading_lbl)

        self._browse_scroll = QScrollArea()
        self._browse_scroll.setWidgetResizable(True)
        self._browse_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._browse_scroll.setFrameShape(QFrame.NoFrame)
        self._browse_scroll.setStyleSheet("background:transparent;border:none;")
        self._browse_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._browse_scroll.setMinimumHeight(200)

        self._browse_inner = QWidget()
        self._browse_inner.setStyleSheet("background:transparent;")
        self._browse_inner_lay = QVBoxLayout(self._browse_inner)
        self._browse_inner_lay.setContentsMargins(0, 0, 0, 0)
        self._browse_inner_lay.setSpacing(3)
        self._browse_inner_lay.addStretch()

        self._browse_scroll.setWidget(self._browse_inner)
        lay.addWidget(self._browse_scroll, 1)
        return page

    def _on_close_album(self) -> None:
        self._browse_top.setVisible(False)
        self.album_panel_closed.emit()

    def is_browse_open(self) -> bool:
        """True when album / playlist track list is visible in the right column."""
        return self._browse_top.isVisible()

    def show_album_browse_loading(self) -> None:
        self._browse_top.setVisible(True)
        self._browse_top.raise_()
        self._browse_title_lbl.setText("Loading…")
        self._browse_count_lbl.setText("")
        self._browse_loading_lbl.setVisible(True)
        self._browse_scroll.setVisible(False)
        self._dl_all_browse_btn.setVisible(False)
        self._dl_sel_btn.setVisible(False)
        self._clear_browse_list()

    def show_album_browse(self, playlist_id: str, tracks: List[Dict]) -> None:
        self._browse_top.setVisible(True)
        self._browse_top.raise_()
        self._browse_loading_lbl.setVisible(False)
        self._browse_scroll.setVisible(True)
        self._dl_all_browse_btn.setVisible(True)
        self._browse_tracks = list(tracks)

        album_title = ""
        if tracks:
            album_title = (tracks[0].get("album") or
                           tracks[0].get("playlist_title") or "")
        if not album_title:
            album_title = "Album"

        self._browse_title_lbl.setText(album_title)
        self._browse_count_lbl.setText(
            f"{len(tracks)} track{'s' if len(tracks) != 1 else ''}")

        self._clear_browse_list()
        self._browse_rows = []
        for i, track in enumerate(tracks):
            row = _BrowseTrackRow(i, track)
            row.play_requested.connect(self._on_browse_track)
            self._browse_inner_lay.insertWidget(i, row)
            self._browse_rows.append(row)

    def _clear_browse_list(self):
        self._browse_rows = []
        while self._browse_inner_lay.count() > 1:
            item = self._browse_inner_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _get_selected_tracks(self) -> List[Dict]:
        return [row._track for row in self._browse_rows if row.is_selected()]

    def _on_browse_track(self, track: dict):
        file_path = (track.get("file_path", "") or track.get("url", "")).strip()
        if not file_path:
            vid = track.get("video_id") or track.get("videoId") or track.get("id")
            if isinstance(vid, dict):
                vid = vid.get("videoId") or vid.get("video_id")
            if vid:
                c = clean_video_id(str(vid).strip())
                if c and len(c) == 11:
                    file_path = f"https://www.youtube.com/watch?v={c}"
        self.browse_track_play_requested.emit(file_path, track)

    def _on_download_all_browse(self):
        if self._browse_tracks:
            self.download_all_album_requested.emit(list(self._browse_tracks))

    def _on_download_selected(self):
        sel = self._get_selected_tracks()
        if sel:
            self.download_all_album_requested.emit(sel)
