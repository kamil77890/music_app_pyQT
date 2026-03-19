"""
MainDashboard — Centre column (Discover page).
Multi-select song cards with Download Selected / Download All buttons.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QScrollArea,
    QSizePolicy,
)

from app.desktop.ui.widgets.artist_circle_widget import ArtistCircleWidget
from app.desktop.ui.widgets.album_card            import AlbumCard
from app.desktop.utils.helpers                    import get_field


# ─── helpers ──────────────────────────────────────────────────────

def _to_dict(entry) -> dict:
    if isinstance(entry, dict):
        return entry
    if hasattr(entry, "model_dump"):
        return entry.model_dump()
    if hasattr(entry, "dict"):
        return entry.dict()
    try:
        return vars(entry)
    except Exception:
        return {}


def _section_row(title: str, show_see_all: bool = True) -> tuple:
    w = QWidget()
    w.setStyleSheet("background:transparent;")
    row = QHBoxLayout(w)
    row.setContentsMargins(0, 0, 0, 0)
    lbl = QLabel(title)
    lbl.setObjectName("section_title")
    row.addWidget(lbl)
    row.addStretch()
    if show_see_all:
        sa = QLabel("See all")
        sa.setObjectName("see_all_link")
        sa.setCursor(Qt.PointingHandCursor)
        row.addWidget(sa)
    return w, row


def _make_h_scroll(height: int) -> tuple:
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    sa.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    sa.setFrameShape(QFrame.NoFrame)
    sa.setFixedHeight(height)
    sa.setStyleSheet("background:transparent;border:none;")
    inner = QWidget()
    inner.setStyleSheet("background:transparent;")
    lay = QHBoxLayout(inner)
    lay.setContentsMargins(0, 4, 0, 4)
    lay.setSpacing(16)
    lay.addStretch()
    sa.setWidget(inner)
    return sa, inner, lay


# ─── MainDashboard ────────────────────────────────────────────────

class MainDashboard(QWidget):
    """
    Signals
    -------
    search_submitted(query: str)
    song_card_double_clicked(file_path: str, metadata: dict)
    song_card_download_clicked(entry: object)   single ▶ button
    download_selected_clicked(songs: list)       selected cards
    download_all_clicked(songs: list)            all visible cards
    album_clicked(playlist_id: str)
    artist_clicked(artist_name: str)
    hero_play_clicked()
    """

    search_submitted           = pyqtSignal(str)
    song_card_double_clicked   = pyqtSignal(str, dict)
    song_card_download_clicked = pyqtSignal(object)
    download_selected_clicked  = pyqtSignal(list)
    download_all_clicked       = pyqtSignal(list)
    album_clicked              = pyqtSignal(str)
    artist_clicked             = pyqtSignal(str)
    hero_play_clicked          = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._song_cards: list       = []
        self._selected_entries: list = []   # plain dicts

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(500)
        self._search_timer.timeout.connect(self._submit_search)

        self._build_ui()

    # ── build ──────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_topbar())

        body_scroll = QScrollArea()
        body_scroll.setWidgetResizable(True)
        body_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body_scroll.setFrameShape(QFrame.NoFrame)
        body_scroll.setStyleSheet("background:transparent;border:none;")

        body = QWidget()
        body.setStyleSheet("background:transparent;")
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(24, 20, 24, 20)
        body_lay.setSpacing(20)

        # ── Daily Artists (hidden until real data) ──
        self._artists_hdr, _ = _section_row("Daily Artists")
        self._artists_hdr.setVisible(False)
        body_lay.addWidget(self._artists_hdr)

        self._artists_sa, self._artists_inner, self._artists_lay = \
            _make_h_scroll(130)
        self._artists_sa.setVisible(False)
        body_lay.addWidget(self._artists_sa)

        # ── Album shelf ──
        self._album_hdr, _ = _section_row("Albums & Playlists",
                                           show_see_all=False)
        self._album_hdr.setVisible(False)
        body_lay.addWidget(self._album_hdr)

        self._album_scroll = QScrollArea()
        self._album_scroll.setWidgetResizable(True)
        self._album_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._album_scroll.setFrameShape(QFrame.NoFrame)
        self._album_scroll.setStyleSheet("background:transparent;border:none;")
        self._album_scroll.setVisible(False)

        self._album_inner = QWidget()
        self._album_inner.setStyleSheet("background:transparent;")
        self._album_inner_lay = QVBoxLayout(self._album_inner)
        self._album_inner_lay.setContentsMargins(0, 0, 0, 0)
        self._album_inner_lay.setSpacing(8)
        self._album_scroll.setWidget(self._album_inner)
        body_lay.addWidget(self._album_scroll)

        # ── Search Results header + action bar ──
        songs_hdr_wrap = QWidget()
        songs_hdr_wrap.setStyleSheet("background:transparent;")
        songs_hdr_row = QHBoxLayout(songs_hdr_wrap)
        songs_hdr_row.setContentsMargins(0, 0, 0, 0)
        songs_hdr_row.setSpacing(8)

        _sl, _ = _section_row("Search Results", show_see_all=False)
        songs_hdr_row.addWidget(_sl, 1)

        # action bar (hidden until results)
        self._action_bar = QWidget()
        self._action_bar.setStyleSheet("background:transparent;")
        self._action_bar.setVisible(False)
        ab_lay = QHBoxLayout(self._action_bar)
        ab_lay.setContentsMargins(0, 0, 0, 0)
        ab_lay.setSpacing(8)

        self._sel_all_btn = QPushButton("Select All")
        self._sel_all_btn.setFixedHeight(32)
        self._sel_all_btn.setStyleSheet(
            "QPushButton{background:#1e1e38;border:1px solid #2a2a50;"
            "border-radius:8px;color:#e8eaf0;font-size:11px;"
            "font-weight:700;padding:0 12px;}"
            "QPushButton:hover{background:#2a2a50;}")
        self._sel_all_btn.clicked.connect(self._select_all)
        ab_lay.addWidget(self._sel_all_btn)

        self._dl_sel_btn = QPushButton("⬇ Download Selected (0)")
        self._dl_sel_btn.setFixedHeight(32)
        self._dl_sel_btn.setEnabled(False)
        self._dl_sel_btn.setStyleSheet(
            "QPushButton{background:#1e1e38;border:1px solid #2a2a50;"
            "border-radius:8px;color:#9395a5;font-size:11px;"
            "font-weight:700;padding:0 12px;}"
            "QPushButton:disabled{color:#3a3a55;border-color:#1e1e38;}"
            "QPushButton:enabled:hover{background:#2a2a50;color:#e8eaf0;}")
        self._dl_sel_btn.clicked.connect(self._emit_download_selected)
        ab_lay.addWidget(self._dl_sel_btn)

        self._dl_all_btn = QPushButton("⬇ Download All")
        self._dl_all_btn.setFixedHeight(32)
        self._dl_all_btn.setStyleSheet(
            "QPushButton{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #4d59fb,stop:1 #6c3aef);border:none;border-radius:8px;"
            "color:#fff;font-size:11px;font-weight:700;padding:0 14px;}"
            "QPushButton:hover{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #5e6aff,stop:1 #7a4aff);}")
        self._dl_all_btn.clicked.connect(self._emit_download_all)
        ab_lay.addWidget(self._dl_all_btn)

        songs_hdr_row.addWidget(self._action_bar)
        body_lay.addWidget(songs_hdr_wrap)

        # song cards horizontal scroll
        self._songs_sa, self._songs_inner, self._songs_lay = \
            _make_h_scroll(290)
        body_lay.addWidget(self._songs_sa)

        # status / empty state
        self._status_lbl = QLabel(
            "Search for songs, artists or playlists above.")
        self._status_lbl.setObjectName("empty_state")
        self._status_lbl.setAlignment(Qt.AlignCenter)
        body_lay.addWidget(self._status_lbl)

        body_lay.addStretch()
        body_scroll.setWidget(body)
        root.addWidget(body_scroll, 1)

    def _build_topbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("topbar")
        bar.setFixedHeight(64)

        lay = QHBoxLayout(bar)
        lay.setContentsMargins(24, 0, 24, 0)
        lay.setSpacing(12)

        sc = QFrame()
        sc.setObjectName("search_container")
        sc.setFixedHeight(44)
        sc.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        sc_lay = QHBoxLayout(sc)
        sc_lay.setContentsMargins(14, 0, 6, 0)
        sc_lay.setSpacing(6)

        search_icon = QLabel("🔍")
        search_icon.setStyleSheet(
            "color:#404060;font-size:14px;background:transparent;")
        sc_lay.addWidget(search_icon)

        self._search_input = QLineEdit()
        self._search_input.setObjectName("search_input")
        self._search_input.setPlaceholderText(
            "Search songs, artists, playlists…")
        self._search_input.setFrame(False)
        self._search_input.textChanged.connect(
            lambda: self._search_timer.start())
        self._search_input.returnPressed.connect(self._submit_search)
        sc_lay.addWidget(self._search_input, 1)

        go_btn = QPushButton("→")
        go_btn.setObjectName("search_go_btn")
        go_btn.setFixedSize(40, 40)
        go_btn.clicked.connect(self._submit_search)
        sc_lay.addWidget(go_btn)

        lay.addWidget(sc, 1)

        for label in ("Chart", "Music Challenges"):
            btn = QPushButton(label)
            btn.setObjectName("topbar_link")
            lay.addWidget(btn)

        lay.addSpacing(8)

        for icon, tip in [("⚙", "Settings"), ("🔔", "Notifications"),
                          ("💬", "Messages")]:
            b = QPushButton(icon)
            b.setObjectName("icon_btn")
            b.setToolTip(tip)
            lay.addWidget(b)

        add_b = QPushButton("+")
        add_b.setObjectName("add_btn")
        add_b.setToolTip("Add")
        lay.addWidget(add_b)

        return bar

    # ── search ─────────────────────────────────────────────────

    def _submit_search(self):
        text = self._search_input.text().strip()
        if text:
            self.search_submitted.emit(text)

    # ── public update API ──────────────────────────────────────

    def set_search_results(
        self,
        songs: list,
        albums: List[Dict],
        playlists: List[Dict],
    ) -> None:
        songs_dicts = [_to_dict(s) for s in songs]
        self._update_song_cards(songs_dicts)
        self._update_album_shelf(albums + playlists)
        self.set_artists(self._extract_artists(songs_dicts))

    def show_loading(self, message: str = "Searching…") -> None:
        self._status_lbl.setText(message)
        self._status_lbl.setVisible(True)
        self._songs_sa.setVisible(False)
        self._action_bar.setVisible(False)
        self._clear_cards()

    def get_search_text(self) -> str:
        return self._search_input.text()

    # ── song cards ─────────────────────────────────────────────

    def _clear_cards(self):
        for card in self._song_cards:
            try:
                card.setParent(None)
                card.deleteLater()
            except Exception:
                pass
        self._song_cards.clear()
        self._selected_entries.clear()
        self._update_dl_btn()

        while self._songs_lay.count() > 1:
            item = self._songs_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _update_song_cards(self, songs: List[Dict]) -> None:
        self._clear_cards()

        if not songs:
            self._status_lbl.setText("No results found.")
            self._status_lbl.setVisible(True)
            self._songs_sa.setVisible(False)
            self._action_bar.setVisible(False)
            return

        self._status_lbl.setVisible(False)
        self._songs_sa.setVisible(True)
        self._action_bar.setVisible(True)

        for entry in songs:
            try:
                from app.desktop.ui.widgets.song_card import SongCard
                entry_dict = _to_dict(entry)
                card = SongCard(entry_dict)
                card._entry_dict = entry_dict   # stash for selection

                # ▶ button → single download
                card.play_btn.clicked.connect(
                    lambda _, e=entry_dict:
                        self.song_card_download_clicked.emit(e)
                )

                # card body click → toggle selection
                _orig_press = card.mousePressEvent
                def _make_toggle(c=card, ed=entry_dict, orig=_orig_press):
                    def _press(ev):
                        if ev.button() == Qt.LeftButton:
                            self._toggle_card(c, ed)
                        orig(ev)
                    return _press
                card.mousePressEvent = _make_toggle()

                self._songs_lay.insertWidget(
                    self._songs_lay.count() - 1, card)
                self._song_cards.append(card)
            except Exception as exc:
                print(f"[MainDashboard] card error: {exc}")

    # ── selection ──────────────────────────────────────────────

    def _toggle_card(self, card, entry_dict: dict):
        if entry_dict in self._selected_entries:
            self._selected_entries.remove(entry_dict)
            card.set_selected(False)
        else:
            self._selected_entries.append(entry_dict)
            card.set_selected(True)
        self._update_dl_btn()

    def _select_all(self):
        self._selected_entries.clear()
        for card in self._song_cards:
            ed = getattr(card, "_entry_dict", None)
            if ed:
                self._selected_entries.append(ed)
                card.set_selected(True)
        self._update_dl_btn()

    def _update_dl_btn(self):
        n = len(self._selected_entries)
        self._dl_sel_btn.setText(f"⬇ Download Selected ({n})")
        self._dl_sel_btn.setEnabled(n > 0)

    def _emit_download_selected(self):
        if self._selected_entries:
            self.download_selected_clicked.emit(list(self._selected_entries))

    def _emit_download_all(self):
        all_e = [getattr(c, "_entry_dict", None) for c in self._song_cards]
        all_e = [e for e in all_e if e]
        if all_e:
            self.download_all_clicked.emit(all_e)

    # ── album shelf ────────────────────────────────────────────

    def _update_album_shelf(self, albums: List[Dict]) -> None:
        while self._album_inner_lay.count():
            item = self._album_inner_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not albums:
            self._album_hdr.setVisible(False)
            self._album_scroll.setVisible(False)
            return

        self._album_hdr.setVisible(True)
        self._album_scroll.setVisible(True)
        self._album_scroll.setFixedHeight(min(len(albums), 3) * 95 + 10)

        for a in albums:
            card = AlbumCard(
                playlist_id   = a["playlist_id"],
                title         = a["title"],
                artist        = a["artist"],
                track_count   = a["track_count"],
                album_type    = a["album_type"],
                thumbnail_url = a["thumbnail_url"],
            )
            card.album_clicked.connect(self.album_clicked)
            card.play_all_requested.connect(self.album_clicked)
            self._album_inner_lay.addWidget(card)

        self._album_inner_lay.addStretch()

    def update_album_card_tracks(
        self, playlist_id: str, tracks: List[Dict]
    ) -> None:
        for i in range(self._album_inner_lay.count()):
            w = self._album_inner_lay.itemAt(i).widget()
            if isinstance(w, AlbumCard) and w.playlist_id == playlist_id:
                w.set_tracks(tracks)
                break

    # ── artists row ────────────────────────────────────────────

    def _extract_artists(self, songs: list) -> List[Dict]:
        seen: set = set()
        out: List[Dict] = []
        for s in songs:
            name = (get_field(s, "artist", "")
                    or get_field(s, "channelTitle", "") or "")
            if name and name not in seen:
                seen.add(name)
                out.append({"name": name})
        return out[:7]

    def set_artists(self, artists: List[Dict]) -> None:
        while self._artists_lay.count() > 1:
            item = self._artists_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not artists:
            self._artists_hdr.setVisible(False)
            self._artists_sa.setVisible(False)
            return

        self._artists_hdr.setVisible(True)
        self._artists_sa.setVisible(True)

        ring_colors = ["#4d59fb", "#6c3aef", "#f0b429", "#e8430a",
                       "#4d59fb", "#6c3aef", "#f0b429"]

        for i, a in enumerate(artists):
            w = ArtistCircleWidget(
                name       = a.get("name", ""),
                diameter   = 76,
                ring_color = ring_colors[i % len(ring_colors)],
            )
            w.clicked.connect(self.artist_clicked)
            px = a.get("pixmap")
            if px:
                w.set_pixmap(px)
            self._artists_lay.insertWidget(i, w)