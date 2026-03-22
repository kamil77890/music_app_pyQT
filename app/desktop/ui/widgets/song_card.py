"""
Song card widget — Spotify-style layout.
Cover improvements: cover_base64 first → maxresdefault URL → hqdefault fallback → placeholder.
"""
import os, re
from typing import Optional
from PyQt5.QtWidgets import QFrame, QVBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget, QHBoxLayout
from PyQt5.QtGui import QPainter, QPen, QColor, QFont, QPixmap, QLinearGradient, QBrush, QImage
from PyQt5.QtCore import Qt, pyqtSignal
from app.desktop.utils.helpers import get_field
from app.desktop.threads.thumbnail_loader import ThumbnailLoader

def _upgrade_yt_url(url):
    if not url or "ytimg.com" not in url:
        return url
    return re.sub(r"/(hq|mq|sd|default)default\.(jpg|webp|png)", r"/maxresdefault.\2", url)

def _hq_url(url):
    return re.sub(r"/maxresdefault\.(jpg|webp|png)", r"/hqdefault.\1", url)

class SongCard(QFrame):
    download_clicked = pyqtSignal(object)

    def __init__(self, entry, parent=None, hide_hover_play_button: bool = False):
        super().__init__(parent)
        if entry is None:
            raise ValueError("Entry cannot be None")
        self.entry = entry
        self._hide_hover_play = bool(hide_hover_play_button)
        self.selected = False
        self.hovered = False
        self.download_status = None
        self.thumbnail_loader: Optional[ThumbnailLoader] = None
        self._thumb_source: Optional[QPixmap] = None
        self._art_h = 170
        self.colors = {'bg':'#181818','bg_hover':'#282828','text_primary':'#FFFFFF',
                       'text_secondary':'#B3B3B3','accent':'#1DB954'}
        self.setup_ui()
        self.load_thumbnail()
        self.update_style()
        self.setFixedHeight(280)
        self.setMinimumWidth(170)

    def setup_ui(self):
        self.setObjectName("song_card")
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        self.art_container = QFrame()
        self.art_container.setFixedHeight(self._art_h)
        self.art_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.art_container.setStyleSheet(
            f"background-color:{self.colors['bg']};border-radius:10px;")
        al = QVBoxLayout(self.art_container)
        al.setContentsMargins(0, 0, 0, 0)
        self.thumb_label = QLabel()
        self.thumb_label.setAlignment(Qt.AlignCenter)
        self.thumb_label.setScaledContents(False)
        self.thumb_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.thumb_label.setMinimumSize(1, 1)
        self.thumb_label.setStyleSheet(
            "background:transparent;border-radius:10px;")
        al.addWidget(self.thumb_label)
        main_layout.addWidget(self.art_container)

        self.play_btn = QPushButton("▶")
        self.play_btn.setFixedSize(44, 44)
        self.play_btn.setStyleSheet(
            f"QPushButton{{background-color:{self.colors['accent']};color:#000;"
            f"border:none;border-radius:22px;font-size:18px;font-weight:bold;}}"
            f"QPushButton:hover{{background-color:#1ED760;}}")
        self.play_btn.setVisible(False)
        self.play_btn.setParent(self)

        text_container = QWidget()
        text_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        text_container.setStyleSheet("background:transparent;border-radius:6px;")
        tl = QVBoxLayout(text_container)
        tl.setContentsMargins(2,0,2,0)
        tl.setSpacing(4)
        title = get_field(self.entry,"title","Unknown Title")
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(
            f"color:{self.colors['text_primary']};font-size:13px;font-weight:700;padding:2px;")
        self.title_label.setWordWrap(True)
        self.title_label.setAlignment(Qt.AlignLeft|Qt.AlignTop)
        self.title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        tl.addWidget(self.title_label)
        artist = get_field(self.entry,"artist","Unknown Artist")
        self.artist_label = QLabel(artist)
        self.artist_label.setStyleSheet(
            f"color:{self.colors['text_secondary']};font-size:11px;")
        self.artist_label.setWordWrap(True)
        self.artist_label.setAlignment(Qt.AlignLeft|Qt.AlignTop)
        self.artist_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        tl.addWidget(self.artist_label)
        main_layout.addWidget(text_container)

        for w in (self.art_container, self.thumb_label, self.title_label,
                  self.artist_label, text_container):
            w.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.play_btn.move(self.width() - 54, 10 + self._art_h - 54)
        self.play_btn.raise_()
        if self._thumb_source is not None and not self._thumb_source.isNull():
            self._apply_thumbnail_scale()

    def load_thumbnail(self):
        b64 = get_field(self.entry,"cover_base64","")
        if b64:
            try:
                import base64
                data = base64.b64decode(b64)
                img = QImage()
                img.loadFromData(data)
                px = QPixmap.fromImage(img)
                if not px.isNull():
                    self.set_thumbnail(px)
                    return
            except Exception: pass
        raw = get_field(self.entry,"cover","") or get_field(self.entry,"thumbnail","") or get_field(self.entry,"high_res_thumbnail","")
        if not raw:
            self.set_placeholder(); return
        self.cleanup_thumbnail_loader()
        self.thumbnail_loader = ThumbnailLoader(_upgrade_yt_url(raw))
        self.thumbnail_loader.loaded.connect(self.set_thumbnail)
        self.thumbnail_loader.error.connect(lambda: self._try_hq(raw))
        self.thumbnail_loader.finished.connect(self.on_thumbnail_loader_finished)
        self.thumbnail_loader.start()

    def _try_hq(self, raw):
        fallback = _hq_url(_upgrade_yt_url(raw))
        if fallback == _upgrade_yt_url(raw):
            self.set_placeholder(); return
        self.cleanup_thumbnail_loader()
        self.thumbnail_loader = ThumbnailLoader(fallback)
        self.thumbnail_loader.loaded.connect(self.set_thumbnail)
        self.thumbnail_loader.error.connect(self.set_placeholder)
        self.thumbnail_loader.finished.connect(self.on_thumbnail_loader_finished)
        self.thumbnail_loader.start()

    def set_thumbnail(self, pixmap: QPixmap):
        if pixmap.isNull():
            self.set_placeholder()
            return
        self._thumb_source = pixmap
        self._apply_thumbnail_scale()

    def _apply_thumbnail_scale(self):
        if self._thumb_source is None or self._thumb_source.isNull():
            return
        w = max(self.thumb_label.width(), self.art_container.width(), 1)
        h = max(self.thumb_label.height(), self._art_h, 1)
        scaled = self._thumb_source.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.thumb_label.setPixmap(scaled)

    def set_placeholder(self, *_):
        self._thumb_source = None
        w = max(self.thumb_label.width(), self.art_container.width(), 170)
        h = max(self.thumb_label.height(), self._art_h, 170)
        px = QPixmap(w, h)
        px.fill(QColor(self.colors['bg']))
        p = QPainter(px)
        if p.isActive():
            p.setRenderHint(QPainter.Antialiasing)
            g = QLinearGradient(0, 0, w, h)
            g.setColorAt(0, QColor("#2a2a3a"))
            g.setColorAt(1, QColor("#12121a"))
            p.setBrush(QBrush(g))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(0, 0, w, h, 10, 10)
            p.setPen(QPen(QColor(self.colors['text_secondary'])))
            p.setFont(QFont("Arial", min(48, w // 4), QFont.Bold))
            p.drawText(px.rect(), Qt.AlignCenter, "♪")
            p.end()
        self.thumb_label.setPixmap(px)

    def on_thumbnail_loader_finished(self):
        if self.thumbnail_loader:
            try:
                self.thumbnail_loader.loaded.disconnect()
                self.thumbnail_loader.error.disconnect()
                self.thumbnail_loader.finished.disconnect()
            except: pass
            self.thumbnail_loader = None

    def cleanup_thumbnail_loader(self):
        if self.thumbnail_loader:
            if self.thumbnail_loader.isRunning(): self.thumbnail_loader.stop()
            try:
                self.thumbnail_loader.loaded.disconnect()
                self.thumbnail_loader.error.disconnect()
                self.thumbnail_loader.finished.disconnect()
            except: pass
            self.thumbnail_loader = None

    def set_download_status(self, status):
        self.download_status = status
        c = {'success':'#1DB954','failed':'#E22134','exists':'#FFD700','downloading':'#1DB954'}.get(status)
        if c:
            self.play_btn.setStyleSheet(
                f"QPushButton{{background-color:{c};color:#000;border:none;"
                f"border-radius:22px;font-size:18px;font-weight:bold;}}"
                f"QPushButton:hover{{background-color:{c};}}")
            self.play_btn.setText({'downloading':'⟳','exists':'✓','failed':'✗'}.get(status,'▶'))
            self.play_btn.setVisible(True)

    def set_selected(self, selected):
        self.selected = selected; self.update_style()

    def enterEvent(self, e):
        self.hovered = True
        self.update_style()
        if not self._hide_hover_play:
            self.play_btn.setVisible(True)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.hovered = False
        self.update_style()
        if not self._hide_hover_play:
            if not self.selected and not self.download_status:
                self.play_btn.setVisible(False)
        super().leaveEvent(e)

    def update_style(self):
        if self.selected:
            bg=self.colors['bg_hover']; b=self.colors['accent']; bw="2px"
        elif self.hovered:
            bg=self.colors['bg_hover']; b="#4d59fb"; bw="1px"
        else:
            bg=self.colors['bg']; b=self.colors['bg']; bw="1px"
        self.setStyleSheet(
            f"QFrame#song_card{{background-color:{bg};border:{bw} solid {b};border-radius:12px;}}")

    def cleanup(self): self.cleanup_thumbnail_loader()
