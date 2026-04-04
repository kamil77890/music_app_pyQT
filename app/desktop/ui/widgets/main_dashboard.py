"""
MainDashboard — Centre column (Discover page)

Changes
───────
  • _ResponsiveSongGrid: cards fill available width, columns auto-calculated
  • Artist click: safe wrapper prevents errors, uses per-closure name capture
  • song_card_double_clicked re-added for backward compat (emitted on dbl-click)
  • Extended/Deluxe albums filtered
  • Select All toggles
  • Refresh Picks topbar button
"""
from __future__ import annotations
import logging
from typing import Dict, List
from PyQt5.QtCore import Qt, QTimer, pyqtSignal

log = logging.getLogger(__name__)
from PyQt5.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QScrollArea, QSizePolicy,
)
from app.desktop.ui.widgets.artist_circle_widget import ArtistCircleWidget
from app.desktop.ui.widgets.album_card import AlbumCard
from app.desktop.utils.helpers import get_field, clean_video_id

_EXTENDED_KW = frozenset([
    "extended","deluxe","special edition","expanded",
    "anniversary edition","remastered edition","complete edition","bonus tracks",
])

def _is_extended(a):
    return any(kw in (a.get("title") or "").lower() for kw in _EXTENDED_KW)

def _to_dict(entry):
    if isinstance(entry, dict): return entry
    for m in ("model_dump","dict"):
        if hasattr(entry, m): return getattr(entry, m)()
    try: return vars(entry)
    except: return {}


def _normalize_youtube_entry(raw) -> dict:
    """Ensure videoId / id are set so downloads & play work after artist-filtered search."""
    d = _to_dict(raw)
    if not isinstance(d, dict):
        d = {}
    else:
        d = dict(d)
    vid = d.get("videoId") or d.get("video_id")
    if isinstance(vid, dict):
        vid = vid.get("videoId") or vid.get("video_id")
    if not vid:
        vid = d.get("id")
    if isinstance(vid, dict):
        vid = vid.get("videoId") or vid.get("video_id")
    # Plain string id from API is often the 11-char video id
    if not vid and isinstance(d.get("id"), str):
        cand = d["id"].strip()
        if len(cand) == 11 and all(c.isalnum() or c in "_-" for c in cand):
            vid = cand
    if vid is not None:
        s = str(vid).strip()
        cleaned = clean_video_id(s) if s else None
        if cleaned:
            if len(cleaned) == 11 and all(
                c.isalnum() or c in "_-" for c in cleaned
            ):
                d["videoId"] = cleaned
                if not d.get("id") or str(d.get("id")) in ("0", ""):
                    d["id"] = cleaned
            else:
                d.setdefault("videoId", s)
    return d


def _coerce_album_row(a) -> dict:
    """Ensure playlist_id / title / artist exist for AlbumCard (API + normalized shapes)."""
    row = dict(a) if isinstance(a, dict) else {}
    pid = (row.get("playlist_id") or "").strip()
    if not pid:
        nested = row.get("id")
        if isinstance(nested, dict):
            pid = (nested.get("playlistId") or nested.get("videoId") or "").strip()
    if not pid:
        pid = (row.get("playlistId") or "").strip()
    row["playlist_id"] = pid
    if not row.get("title"):
        sn = row.get("snippet") or {}
        row["title"] = sn.get("title") or row.get("title") or "Album"
    if not row.get("artist"):
        sn = row.get("snippet") or {}
        row["artist"] = sn.get("channelTitle") or row.get("artist") or ""
    tc = row.get("track_count", 0)
    if not tc and row.get("contentDetails"):
        tc = row["contentDetails"].get("itemCount") or 0
    row["track_count"] = int(tc) if tc else 0
    if not row.get("thumbnail_url"):
        sn = row.get("snippet") or {}
        th = sn.get("thumbnails") or {}
        row["thumbnail_url"] = (
            (th.get("high") or {}).get("url")
            or (th.get("medium") or {}).get("url")
            or (th.get("default") or {}).get("url")
            or ""
        )
    if not row.get("album_type"):
        row["album_type"] = "ALBUM"
    return row


def _youtube_url_if_no_file(d: dict) -> str:
    fp = (d.get("file_path") or d.get("path") or d.get("url") or "").strip()
    if fp:
        return fp
    vid = d.get("videoId") or d.get("video_id") or d.get("id")
    if isinstance(vid, dict):
        vid = vid.get("videoId") or vid.get("video_id")
    if vid:
        c = clean_video_id(str(vid).strip())
        if c and len(c) == 11:
            return f"https://www.youtube.com/watch?v={c}"
    return ""

def _section_header(title):
    w = QWidget(); w.setStyleSheet("background:transparent;")
    row = QHBoxLayout(w); row.setContentsMargins(0,0,0,0)
    lbl = QLabel(title); lbl.setObjectName("section_title")
    row.addWidget(lbl); row.addStretch()
    return w

def _make_h_scroll(height):
    sa = QScrollArea(); sa.setWidgetResizable(True)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    sa.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    sa.setFrameShape(QFrame.NoFrame); sa.setFixedHeight(height)
    sa.setStyleSheet("background:transparent;border:none;")
    inner = QWidget(); inner.setStyleSheet("background:transparent;")
    lay = QHBoxLayout(inner); lay.setContentsMargins(0,4,0,4); lay.setSpacing(16); lay.addStretch()
    sa.setWidget(inner)
    return sa, inner, lay


# ─────────────────────────────────────────────────────────────────
#  Responsive song grid — fills available width
# ─────────────────────────────────────────────────────────────────
class _ResponsiveSongGrid(QWidget):
    """Manual-geometry container: card widths fill the row automatically."""

    MIN_CARD_W = 180
    CARD_H     = 280
    SPACING    = 14

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")
        self._cards: list = []

    def set_cards(self, cards: list):
        for c in self._cards:
            try: c.setParent(None)
            except: pass
        self._cards = list(cards)
        for c in self._cards:
            c.setParent(self); c.show()
        self._relayout()

    def clear(self):
        for c in self._cards:
            try: c.deleteLater()
            except: pass
        self._cards.clear()
        self.setMinimumHeight(0); self.setMaximumHeight(16_777_215)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout()

    def _cols(self):
        return max(1, (max(self.width(),1) + self.SPACING) // (self.MIN_CARD_W + self.SPACING))

    def _card_w(self):
        cols = self._cols()
        return max(self.MIN_CARD_W, (self.width() - (cols-1)*self.SPACING) // cols)

    def _relayout(self):
        if not self._cards:
            self.setMinimumHeight(0); return
        cols = self._cols(); cw = self._card_w()
        for i, card in enumerate(self._cards):
            row = i//cols; col = i%cols
            card.setFixedSize(cw, self.CARD_H)
            card.move(col*(cw+self.SPACING), row*(self.CARD_H+self.SPACING))
        rows = (len(self._cards)+cols-1)//cols
        h = rows*self.CARD_H + (rows-1)*self.SPACING + 10
        self.setMinimumHeight(h); self.setMaximumHeight(h)


# ─────────────────────────────────────────────────────────────────
#  MainDashboard
# ─────────────────────────────────────────────────────────────────
class MainDashboard(QWidget):
    search_submitted           = pyqtSignal(str)
    song_card_double_clicked   = pyqtSignal(str, dict)   # backward compat
    song_card_download_clicked = pyqtSignal(object)
    download_selected_clicked  = pyqtSignal(list)
    download_all_clicked       = pyqtSignal(list)
    album_clicked              = pyqtSignal(str)
    artist_clicked             = pyqtSignal(str)
    refresh_requested          = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._song_cards:  list = []
        self._all_entries: list = []
        self._selected:    list = []
        self._all_selected       = False
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(500)
        self._search_timer.timeout.connect(self._submit_search)
        self._build_ui()

    # ── build ──────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0,0,0,0); root.setSpacing(0)
        root.addWidget(self._build_topbar())

        body_scroll = QScrollArea(); body_scroll.setWidgetResizable(True)
        body_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body_scroll.setFrameShape(QFrame.NoFrame)
        body_scroll.setStyleSheet("background:transparent;border:none;")

        body = QWidget(); body.setStyleSheet("background:transparent;")
        blay = QVBoxLayout(body)
        blay.setContentsMargins(24,20,24,20); blay.setSpacing(20)

        # Artists
        self._artists_hdr = _section_header("Daily Artists")
        self._artists_hdr.setVisible(False)
        blay.addWidget(self._artists_hdr)
        self._artists_sa, self._artists_inner, self._artists_lay = _make_h_scroll(130)
        self._artists_sa.setVisible(False)
        blay.addWidget(self._artists_sa)

        # Albums
        self._album_hdr = _section_header("Albums & Playlists")
        self._album_hdr.setVisible(False); blay.addWidget(self._album_hdr)
        self._album_scroll = QScrollArea(); self._album_scroll.setWidgetResizable(True)
        self._album_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._album_scroll.setFrameShape(QFrame.NoFrame)
        self._album_scroll.setStyleSheet("background:transparent;border:none;")
        self._album_scroll.setVisible(False)
        self._album_inner = QWidget(); self._album_inner.setStyleSheet("background:transparent;")
        self._album_inner_lay = QVBoxLayout(self._album_inner)
        self._album_inner_lay.setContentsMargins(0,0,0,0); self._album_inner_lay.setSpacing(8)
        self._album_scroll.setWidget(self._album_inner)
        blay.addWidget(self._album_scroll)

        # Songs header + action bar
        shw = QWidget(); shw.setStyleSheet("background:transparent;")
        shr = QHBoxLayout(shw); shr.setContentsMargins(0,0,0,0); shr.setSpacing(8)
        shr.addWidget(_section_header("Search Results"), 1)

        self._action_bar = QWidget(); self._action_bar.setStyleSheet("background:transparent;")
        self._action_bar.setVisible(False)
        ab = QHBoxLayout(self._action_bar); ab.setContentsMargins(0,0,0,0); ab.setSpacing(8)

        self._sel_all_btn = QPushButton("Select All"); self._sel_all_btn.setFixedHeight(32)
        self._sel_all_btn.setStyleSheet(
            "QPushButton{background:#1e1e38;border:1px solid #2a2a50;border-radius:8px;"
            "color:#e8eaf0;font-size:11px;font-weight:700;padding:0 12px;}"
            "QPushButton:hover{background:#2a2a50;}"
            "QPushButton[active='true']{background:#4d59fb;border-color:#4d59fb;color:#fff;}")
        self._sel_all_btn.clicked.connect(self._toggle_select_all)
        ab.addWidget(self._sel_all_btn)

        self._dl_sel_btn = QPushButton("⬇ Download Selected (0)"); self._dl_sel_btn.setFixedHeight(32)
        self._dl_sel_btn.setEnabled(False)
        self._dl_sel_btn.setStyleSheet(
            "QPushButton{background:#1e1e38;border:1px solid #2a2a50;border-radius:8px;"
            "color:#9395a5;font-size:11px;font-weight:700;padding:0 12px;}"
            "QPushButton:disabled{color:#3a3a55;border-color:#1e1e38;}"
            "QPushButton:enabled:hover{background:#2a2a50;color:#e8eaf0;}")
        self._dl_sel_btn.clicked.connect(self._emit_download_selected)
        ab.addWidget(self._dl_sel_btn)

        self._dl_all_btn = QPushButton("⬇ Download All"); self._dl_all_btn.setFixedHeight(32)
        self._dl_all_btn.setStyleSheet(
            "QPushButton{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #4d59fb,stop:1 #6c3aef);border:none;border-radius:8px;"
            "color:#fff;font-size:11px;font-weight:700;padding:0 14px;}"
            "QPushButton:hover{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #5e6aff,stop:1 #7a4aff);}")
        self._dl_all_btn.clicked.connect(self._emit_download_all)
        ab.addWidget(self._dl_all_btn)

        shr.addWidget(self._action_bar); blay.addWidget(shw)

        # Responsive song grid
        self._songs_scroll = QScrollArea(); self._songs_scroll.setWidgetResizable(True)
        self._songs_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._songs_scroll.setFrameShape(QFrame.NoFrame)
        self._songs_scroll.setStyleSheet("background:transparent;border:none;")
        self._songs_scroll.setVisible(False)
        self._song_grid = _ResponsiveSongGrid()
        self._songs_scroll.setWidget(self._song_grid)
        blay.addWidget(self._songs_scroll, 1)

        self._status_lbl = QLabel("Search for songs, artists or playlists above.")
        self._status_lbl.setObjectName("empty_state"); self._status_lbl.setAlignment(Qt.AlignCenter)
        blay.addWidget(self._status_lbl)
        blay.addStretch()
        body_scroll.setWidget(body); root.addWidget(body_scroll, 1)

    def _build_topbar(self):
        bar = QFrame(); bar.setObjectName("topbar"); bar.setFixedHeight(64)
        lay = QHBoxLayout(bar); lay.setContentsMargins(24,0,24,0); lay.setSpacing(12)

        sc = QFrame(); sc.setObjectName("search_container"); sc.setFixedHeight(44)
        sc.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        sl = QHBoxLayout(sc); sl.setContentsMargins(14,0,6,0); sl.setSpacing(6)
        si = QLabel("🔍"); si.setStyleSheet("color:#404060;font-size:14px;background:transparent;")
        sl.addWidget(si)
        self._search_input = QLineEdit(); self._search_input.setObjectName("search_input")
        self._search_input.setPlaceholderText("Search songs, artists, playlists…")
        self._search_input.setFrame(False)
        self._search_input.setStyleSheet(
            "QLineEdit{font-family:'JetBrains Mono','Fira Code','Cascadia Code','Consolas',monospace;"
            "font-size:14px;font-style:italic;letter-spacing:0.3px;color:#e8eaf0;"
            "background:transparent;border:none;}")
        self._search_input.textChanged.connect(lambda: self._search_timer.start())
        self._search_input.returnPressed.connect(self._submit_search)
        sl.addWidget(self._search_input, 1)
        go = QPushButton("→"); go.setObjectName("search_go_btn"); go.setFixedSize(40,40)
        go.clicked.connect(self._submit_search); sl.addWidget(go)
        lay.addWidget(sc, 1)

        rfr = QPushButton("🔄 Refresh Picks"); rfr.setObjectName("topbar_link")
        rfr.setToolTip("Refresh recommendations from your library")
        rfr.clicked.connect(self.refresh_requested); lay.addWidget(rfr)
        return bar

    # ── search ──────────────────────────────────────────────────

    def _submit_search(self):
        t = self._search_input.text().strip()
        if t: self.search_submitted.emit(t)

    # ── public API ───────────────────────────────────────────────

    def set_search_results(self, songs, albums, playlists, artist_filter=None):
        dicts = [_normalize_youtube_entry(s) for s in songs]
        combined_albums = list(albums) + list(playlists)
        if artist_filter:
            af = artist_filter.lower().strip()

            def _song_match(d):
                art = (get_field(d, "artist", "") or get_field(d, "channelTitle", "") or "")
                return af in art.lower()

            def _song_match_loose(d):
                title = (get_field(d, "title", "") or "").lower()
                art = (get_field(d, "artist", "") or get_field(d, "channelTitle", "") or "").lower()
                if af in art or af in title:
                    return True
                for tok in af.split():
                    if len(tok) > 2 and (tok in art or tok in title):
                        return True
                return False

            def _alb_match(a):
                art = (a.get("artist") or
                       (a.get("snippet") or {}).get("channelTitle") or "")
                return af in art.lower()

            original = list(dicts)
            dicts = [d for d in dicts if _song_match(d)]
            if not dicts:
                dicts = [d for d in original if _song_match_loose(d)]
            if not dicts:
                dicts = original[:20]
            combined_albums = [a for a in combined_albums if _alb_match(a)]
        self._update_song_grid(dicts)
        self._update_album_shelf(combined_albums)

    def set_daily_artists_from_library(self, artists: List[Dict]):
        """Daily Artists row — from local library counts, not from YouTube search."""
        self.set_artists(artists)

    def show_loading(self, message="Searching…"):
        self._status_lbl.setText(message); self._status_lbl.setVisible(True)
        self._songs_scroll.setVisible(False); self._action_bar.setVisible(False)
        self._clear_grid()

    def get_search_text(self):
        return self._search_input.text()

    # ── song grid ────────────────────────────────────────────────

    def _clear_grid(self):
        self._song_grid.clear(); self._song_cards.clear()
        self._all_entries.clear(); self._selected.clear()
        self._all_selected = False
        self._update_sel_btn_label(); self._update_dl_btn()

    def _update_song_grid(self, songs):
        self._clear_grid()
        if not songs:
            self._status_lbl.setText("No results found."); self._status_lbl.setVisible(True)
            self._songs_scroll.setVisible(False); self._action_bar.setVisible(False); return

        self._status_lbl.setVisible(False)
        self._songs_scroll.setVisible(True); self._action_bar.setVisible(True)
        self._all_entries = list(songs)

        from app.desktop.ui.widgets.song_card import SongCard
        for entry in songs:
            try:
                card = SongCard(entry, hide_hover_play_button=True)
                card._entry_dict = entry
                # ▶ = download
                card.play_btn.clicked.connect(
                    lambda _, e=entry: self.song_card_download_clicked.emit(e))
                # click = toggle select
                orig = card.mousePressEvent
                def _h(ev, c=card, ed=entry, o=orig):
                    if ev.button() == Qt.LeftButton: self._toggle_card(c, ed)
                    o(ev)
                card.mousePressEvent = _h
                # double-click = play (YouTube: use watch URL from video id)
                def _dbl(ev, ed=entry):
                    if ev.button() != Qt.LeftButton:
                        return
                    fp = _youtube_url_if_no_file(ed)
                    if fp:
                        self.song_card_double_clicked.emit(fp, ed)
                card.mouseDoubleClickEvent = _dbl
                self._song_cards.append(card)
            except Exception as exc:
                log.warning("Song card creation error: %s", exc)
        self._song_grid.set_cards(self._song_cards)

    # ── selection ────────────────────────────────────────────────

    def _toggle_card(self, card, entry):
        if entry in self._selected:
            self._selected.remove(entry); card.set_selected(False)
        else:
            self._selected.append(entry); card.set_selected(True)
        self._all_selected = len(self._selected) == len(self._all_entries) > 0
        self._update_sel_btn_label(); self._update_dl_btn()

    def _toggle_select_all(self):
        if self._all_selected:
            self._selected.clear()
            for c in self._song_cards: c.set_selected(False)
            self._all_selected = False
        else:
            self._selected = list(self._all_entries)
            for c in self._song_cards: c.set_selected(True)
            self._all_selected = True
        self._update_sel_btn_label(); self._update_dl_btn()

    def _update_sel_btn_label(self):
        if self._all_selected:
            self._sel_all_btn.setText("Deselect All"); self._sel_all_btn.setProperty("active","true")
        else:
            self._sel_all_btn.setText("Select All"); self._sel_all_btn.setProperty("active","false")
        self._sel_all_btn.style().unpolish(self._sel_all_btn)
        self._sel_all_btn.style().polish(self._sel_all_btn)

    def _update_dl_btn(self):
        n = len(self._selected)
        self._dl_sel_btn.setText(f"⬇ Download Selected ({n})")
        self._dl_sel_btn.setEnabled(n > 0)

    def _emit_download_selected(self):
        if self._selected: self.download_selected_clicked.emit(list(self._selected))

    def _emit_download_all(self):
        if self._all_entries: self.download_all_clicked.emit(list(self._all_entries))

    # ── album shelf ──────────────────────────────────────────────

    def _update_album_shelf(self, albums):
        while self._album_inner_lay.count():
            item = self._album_inner_lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        filtered = [a for a in albums if not _is_extended(a)]
        if not filtered:
            self._album_hdr.setVisible(False); self._album_scroll.setVisible(False); return
        self._album_hdr.setVisible(True); self._album_scroll.setVisible(True)
        self._album_scroll.setFixedHeight(min(len(filtered),3)*98+10)
        for a in filtered:
            try:
                row = _coerce_album_row(a)
                if not row.get("playlist_id"):
                    log.warning("Skipping album row without playlist_id: %s", row.get("title"))
                    continue
                card = AlbumCard(
                    playlist_id=row["playlist_id"],
                    title=row.get("title", ""),
                    artist=row.get("artist", ""),
                    track_count=row.get("track_count", 0),
                    album_type=row.get("album_type", "ALBUM"),
                    thumbnail_url=row.get("thumbnail_url", ""),
                )
                card.album_clicked.connect(self.album_clicked)
                self._album_inner_lay.addWidget(card)
            except Exception as exc:
                log.warning("Album card creation error: %s", exc)
        self._album_inner_lay.addStretch()

    def update_album_card_tracks(self, playlist_id, tracks):
        for i in range(self._album_inner_lay.count()):
            w = self._album_inner_lay.itemAt(i).widget()
            if isinstance(w, AlbumCard) and w.playlist_id == playlist_id:
                w.set_tracks(tracks); break

    # ── artists ──────────────────────────────────────────────────

    def _extract_artists(self, songs):
        seen = set(); out = []
        for s in songs:
            n = get_field(s,"artist","") or get_field(s,"channelTitle","") or ""
            if n and n not in seen:
                seen.add(n); out.append({"name": n})
        return out[:7]

    def set_artists(self, artists):
        while self._artists_lay.count() > 1:
            item = self._artists_lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        if not artists:
            self._artists_hdr.setVisible(False); self._artists_sa.setVisible(False); return
        self._artists_hdr.setVisible(True); self._artists_sa.setVisible(True)
        ring_colors = ["#4d59fb","#6c3aef","#f0b429","#e8430a","#4d59fb","#6c3aef","#f0b429"]
        for i, a in enumerate(artists):
            try:
                w = ArtistCircleWidget(name=a.get("name",""), diameter=76,
                                       ring_color=ring_colors[i % len(ring_colors)])
                # FIX: capture name in closure explicitly, emit through safe wrapper
                _name = a.get("name", "")
                sc = a.get("song_count")
                if sc is not None:
                    w.setToolTip(f"{_name}\n{sc} song(s) in your library")
                def _click_handler(n=_name):
                    try:
                        if n: self.artist_clicked.emit(n)
                    except Exception as exc:
                        log.error("Artist emit error: %s", exc)
                w.clicked.connect(_click_handler)
                px = a.get("pixmap")
                if px: w.set_pixmap(px)
                self._artists_lay.insertWidget(i, w)
            except Exception as exc:
                log.warning("Artist widget creation error: %s", exc)