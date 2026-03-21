"""
MusicFlow — Dark Streaming Theme QSS
─────────────────────────────────────
Changes
  • search_input: monospace italic font
  • Queue rows: airier spacing, 2px accent border for selected/current
  • diagonal_song_row removed (back to SongCard grid)
  • Local playlist top-row cards: hover accent border
  • album_card_frame: selected state with accent border
"""

STYLESHEET = """
* { outline: none; }

QMainWindow, QWidget {
    background-color: #0b0b0b;
    color: #e8eaf0;
    font-family: 'Segoe UI', system-ui, sans-serif;
    font-size: 13px;
}

QDialog {
    background-color: #111118;
    color: #e8eaf0;
    font-family: 'Segoe UI', system-ui, sans-serif;
    border: 1px solid #1e1e2e;
    border-radius: 16px;
}

/* ── SIDEBAR ─────────────────────────────────── */

QFrame#sidebar {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #0a0a14, stop:1 #060610);
    border-right: 1px solid #18182a;
}

QFrame#sidebar_divider {
    background-color: #1a1a2e;
    margin: 0 14px;
}

QScrollArea#sidebar_scroll {
    background: transparent;
    border: none;
}
QScrollArea#sidebar_scroll QScrollBar:vertical {
    background: transparent;
    width: 5px;
    margin: 2px 0;
    border-radius: 2px;
}
QScrollArea#sidebar_scroll QScrollBar::handle:vertical {
    background: #2a2a44;
    border-radius: 2px;
    min-height: 30px;
}
QScrollArea#sidebar_scroll QScrollBar::add-line:vertical,
QScrollArea#sidebar_scroll QScrollBar::sub-line:vertical {
    height: 0;
}

QLabel#sidebar_section {
    color: #4a4a65;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.5px;
    background: transparent;
}

QLabel#daily_artist_name {
    color: #9395a5;
    font-size: 12px;
    font-weight: 500;
    background: transparent;
}

QLabel#sidebar_lib_count {
    color: #4d59fb;
    font-size: 11px;
    font-weight: 700;
    background: transparent;
    padding: 2px 7px;
    border-radius: 8px;
}

QLabel#sidebar_empty_hint {
    color: #4a4a65;
    font-size: 11px;
    font-weight: 500;
    background: transparent;
    padding: 12px 14px 12px 14px;
}

/* ── NAV ITEMS ─────────────────────────────── */

QFrame#nav_item {
    background: transparent;
    border: none;
    border-radius: 10px;
    min-height: 44px;
}
QFrame#nav_item:hover {
    background-color: #111120;
}
QFrame#nav_item[active="true"] {
    background-color: #14142a;
    border-left: 3px solid #4d59fb;
}

QLabel#nav_item_icon {
    color: #5c5f78;
    font-size: 16px;
    background: transparent;
}
QFrame#nav_item[active="true"] QLabel#nav_item_icon {
    color: #4d59fb;
}

QLabel#nav_item_title {
    color: #b0b4c8;
    font-size: 13px;
    font-weight: 600;
    background: transparent;
}
QFrame#nav_item:hover QLabel#nav_item_title { color: #e0e4f0; }
QFrame#nav_item[active="true"] QLabel#nav_item_title { color: #c8ccff; }

QLabel#nav_item_sub {
    color: #4a4a65;
    font-size: 10px;
    font-weight: 500;
    background: transparent;
}

/* ── LIBRARY ROWS ────────────────────────────── */

QFrame#sidebar_lib_row {
    background-color: transparent;
    border: none;
    border-radius: 8px;
}
QFrame#sidebar_lib_row:hover {
    background-color: #111120;
}

QLabel#sidebar_lib_icon {
    color: #3a3a55;
    font-size: 13px;
    background: transparent;
}
QFrame#sidebar_lib_row:hover QLabel#sidebar_lib_icon {
    color: #4d59fb;
}

QLabel#sidebar_lib_label {
    color: #8a8eaa;
    font-size: 12px;
    font-weight: 500;
    background: transparent;
}
QFrame#sidebar_lib_row:hover QLabel#sidebar_lib_label {
    color: #c8ccdd;
}

/* ── TOP BAR ─────────────────────────────────── */

QFrame#topbar {
    background-color: #0b0b0b;
    border-bottom: 1px solid #141424;
}

QFrame#search_container {
    background-color: #141424;
    border: 1px solid #1e1e38;
    border-radius: 22px;
}

/* Monospace italic — distinct from the rest of the UI */
QLineEdit#search_input {
    background: transparent;
    border: none;
    color: #e8eaf0;
    font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code',
                 'Consolas', 'Courier New', monospace;
    font-size: 14px;
    font-style: italic;
    letter-spacing: 0.3px;
    padding: 0 4px;
    selection-background-color: #4d59fb;
    selection-color: #ffffff;
}

QPushButton#search_go_btn {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 #4d59fb, stop:1 #6c3aef);
    border: none;
    border-radius: 18px;
    color: #ffffff;
    font-size: 15px;
    font-weight: 700;
    min-width: 40px; min-height: 40px;
    max-width: 40px; max-height: 40px;
    padding: 0;
}
QPushButton#search_go_btn:hover {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 #5e6aff, stop:1 #7a4aff);
}

QPushButton#topbar_link {
    background: transparent;
    border: none;
    color: #6e7080;
    font-size: 13px;
    font-weight: 600;
    padding: 6px 12px;
    min-height: 0;
}
QPushButton#topbar_link:hover { color: #e8eaf0; }

QPushButton#icon_btn {
    background: transparent;
    border: 1px solid #1e1e38;
    border-radius: 20px;
    color: #9395a5;
    font-size: 15px;
    min-width: 38px; min-height: 38px;
    max-width: 38px; max-height: 38px;
    padding: 0;
}
QPushButton#icon_btn:hover {
    background-color: #141424;
    color: #e8eaf0;
    border-color: #4d59fb;
}

QPushButton#add_btn {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 #4d59fb, stop:1 #6c3aef);
    border: none;
    border-radius: 20px;
    color: #ffffff;
    font-size: 18px;
    font-weight: 700;
    min-width: 38px; min-height: 38px;
    max-width: 38px; max-height: 38px;
    padding: 0;
}

/* ── SCROLL AREAS ────────────────────────────── */

QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }

/* ── SECTION LABELS ──────────────────────────── */

QLabel#section_title {
    color: #e8eaf0;
    font-size: 18px;
    font-weight: 800;
    letter-spacing: -0.3px;
    background: transparent;
}

QLabel#see_all_link {
    color: #4d59fb;
    font-size: 12px;
    font-weight: 700;
    background: transparent;
}

QLabel#empty_state {
    color: #3a3a60;
    font-size: 14px;
    font-weight: 500;
    background: transparent;
}

/* ── SONG CARDS ──────────────────────────────── */

QFrame#song_card {
    background-color: #111118;
    border: 1px solid transparent;
    border-radius: 15px;
}
QFrame#song_card:hover {
    background-color: #181828;
    border: 1px solid #2a2a50;
}

QLabel#card_title {
    color: #e8eaf0; font-size: 12px; font-weight: 700; background: transparent;
}
QLabel#card_subtitle {
    color: #6e7080; font-size: 11px; background: transparent;
}

QPushButton#card_play_btn {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 #4d59fb, stop:1 #6c3aef);
    border: none;
    border-radius: 22px;
    color: #ffffff;
    font-size: 16px;
    font-weight: 700;
    min-width: 44px; min-height: 44px;
    max-width: 44px; max-height: 44px;
    padding: 0;
}

/* ── ALBUM CARD ──────────────────────────────── */

QFrame#album_card_frame {
    background-color: #111118;
    border: 1px solid transparent;
    border-radius: 15px;
}

/* Selected / active album: 2px accent border */
QFrame#album_card_frame[selected="true"] {
    background-color: #181830;
    border: 2px solid #4d59fb;
}

QLabel#album_type_badge {
    background: #1e1e38;
    color: #4d59fb;
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 1px;
    border-radius: 4px;
    padding: 2px 6px;
}
QLabel#album_card_title {
    color: #e8eaf0; font-size: 13px; font-weight: 700; background: transparent;
}
QLabel#album_card_artist {
    color: #9395a5; font-size: 11px; background: transparent;
}
QLabel#album_track_count {
    color: #4a4a65; font-size: 10px; background: transparent;
}

/* ── PLAYLIST CARD (local playlists row) ─────── */

QFrame#playlist_card {
    background-color: #111118;
    border: 1px solid transparent;
    border-radius: 12px;
}
QFrame#playlist_card:hover {
    background-color: #181828;
    border: 1px solid #2a2a50;
}

/* ── NOW PLAYING PANEL ───────────────────────── */

QFrame#now_playing_panel {
    background-color: #080810;
    border-left: 1px solid #141424;
}

QLabel#np_label_small {
    color: #3a3a55;
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 1.5px;
    background: transparent;
}
QLabel#np_track_title {
    color: #ffffff;
    font-size: 16px;
    font-weight: 800;
    background: transparent;
}
QLabel#np_artist_name {
    color: #4d59fb;
    font-size: 12px;
    font-weight: 600;
    background: transparent;
}
QLabel#np_time_label {
    color: #4a4a65;
    font-size: 11px;
    background: transparent;
}

/* Progress slider */
QSlider#np_progress::groove:horizontal {
    background-color: #1e1e38; height: 4px; border-radius: 2px;
}
QSlider#np_progress::handle:horizontal {
    background-color: #f0b429;
    width: 14px; height: 14px; margin: -5px 0;
    border-radius: 7px; border: none;
}
QSlider#np_progress::sub-page:horizontal {
    background-color: #f0b429; border-radius: 2px;
}

/* Playback buttons */
QPushButton#ctrl_btn {
    background: transparent;
    border: none;
    color: #4a4a65;
    font-size: 16px;
    min-width: 36px; min-height: 36px;
    max-width: 36px; max-height: 36px;
    border-radius: 18px;
    padding: 0;
}
QPushButton#ctrl_btn:hover {
    color: #e8eaf0; background-color: #141424;
}
QPushButton#ctrl_btn[active="true"] { color: #4d59fb; }

QPushButton#play_pause_btn {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 #f0b429, stop:1 #e8850a);
    border: none;
    border-radius: 28px;
    color: #000000;
    font-size: 20px;
    min-width: 56px; min-height: 56px;
    max-width: 56px; max-height: 56px;
    padding: 0;
}
QPushButton#play_pause_btn:hover {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 #ffd166, stop:1 #f0a020);
}

/* Volume slider */
QSlider#vol_slider::groove:horizontal {
    background-color: #1e1e38; height: 3px; border-radius: 2px;
}
QSlider#vol_slider::sub-page:horizontal {
    background-color: #4d59fb; border-radius: 2px;
}
QSlider#vol_slider::handle:horizontal {
    background-color: #ffffff;
    width: 12px; height: 12px; margin: -5px 0;
    border-radius: 6px; border: none;
}

/* ── QUEUE ROWS ──────────────────────────────── */

QLabel#queue_header {
    color: #e8eaf0; font-size: 13px; font-weight: 800; background: transparent;
}
QLabel#queue_track_title {
    color: #e8eaf0; font-size: 12px; font-weight: 600; background: transparent;
}
QLabel#queue_track_artist {
    color: #4a4a65; font-size: 10px; background: transparent;
}
QLabel#queue_track_duration {
    color: #4a4a65; font-size: 10px; background: transparent;
}

/* ── SCROLLBARS ──────────────────────────────── */

QScrollBar:vertical {
    background: transparent; width: 6px; margin: 0;
}
QScrollBar::handle:vertical {
    background-color: #202038; border-radius: 3px; min-height: 30px;
}
QScrollBar::handle:vertical:hover { background-color: #4d59fb; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

QScrollBar:horizontal {
    background: transparent; height: 6px; margin: 0;
}
QScrollBar::handle:horizontal {
    background-color: #202038; border-radius: 3px; min-width: 30px;
}
QScrollBar::handle:horizontal:hover { background-color: #4d59fb; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ── TREE / LIST ─────────────────────────────── */

QTreeWidget, QListWidget {
    background: transparent; border: none; outline: none; font-size: 12px;
}
QTreeWidget::item, QListWidget::item {
    padding: 8px 12px; border-radius: 8px;
    color: #6e7080; margin: 1px 4px;
}
QTreeWidget::item:selected, QListWidget::item:selected {
    background-color: #181830; color: #e8eaf0;
}
QTreeWidget::item:hover:!selected, QListWidget::item:hover:!selected {
    background-color: #111120; color: #c0c4d8;
}

/* ── GENERAL BUTTONS ─────────────────────────── */

QPushButton {
    background-color: #141424;
    border: 1px solid #1e1e38;
    border-radius: 10px;
    color: #9395a5;
    font-size: 12px;
    font-weight: 600;
    padding: 8px 16px;
    min-height: 36px;
}
QPushButton:hover {
    background-color: #1a1a30; color: #e8eaf0; border-color: #2e2e55;
}
QPushButton:pressed { background-color: #111120; }
QPushButton:disabled {
    background-color: #0d0d18; color: #2a2a42; border-color: #141424;
}
QPushButton[style="primary"] {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 #4d59fb, stop:1 #6c3aef);
    border: none;
    color: #ffffff;
    font-weight: 700;
    border-radius: 12px;
}
QPushButton[style="primary"]:hover {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 #5e6aff, stop:1 #7a4aff);
}

/* ── INPUTS ──────────────────────────────────── */

QLineEdit {
    background-color: #111118;
    border: 1px solid #1e1e38;
    border-radius: 10px;
    color: #e8eaf0;
    font-size: 13px;
    padding: 8px 14px;
    selection-background-color: #4d59fb;
    selection-color: #ffffff;
}
QLineEdit:focus {
    border: 1px solid #4d59fb; background-color: #141424;
}

/* ── TOOLTIPS / MENUS ────────────────────────── */

QToolTip {
    background-color: #111118;
    border: 1px solid #2a2a50;
    border-radius: 8px;
    color: #e8eaf0;
    padding: 6px 10px;
    font-size: 11px;
}

QMenu {
    background-color: #111118;
    border: 1px solid #1e1e38;
    border-radius: 12px;
    padding: 6px;
}
QMenu::item {
    padding: 9px 32px 9px 14px; border-radius: 6px;
    color: #9395a5; margin: 1px;
}
QMenu::item:selected { background-color: #181830; color: #e8eaf0; }
QMenu::separator {
    height: 1px; background-color: #1e1e38; margin: 4px 8px;
}

/* ── GROUP BOXES ─────────────────────────────── */

QGroupBox {
    color: #6e7080;
    font-weight: 700;
    font-size: 11px;
    letter-spacing: 0.5px;
    border: 1px solid #1e1e38;
    border-radius: 12px;
    margin-top: 14px;
    padding-top: 14px;
    background-color: #0d0d18;
}
QGroupBox::title {
    subcontrol-origin: margin; left: 12px;
    padding: 0 8px; color: #4d59fb;
}

/* ── CHECKBOXES ──────────────────────────────── */

QCheckBox { color: #9395a5; font-size: 12px; spacing: 8px; }
QCheckBox::indicator {
    width: 18px; height: 18px;
    border: 1px solid #2a2a50;
    border-radius: 5px;
    background: #111118;
}
QCheckBox::indicator:checked {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 #4d59fb, stop:1 #6c3aef);
    border-color: transparent;
}

/* ── SPLITTER ────────────────────────────────── */

QSplitter::handle { background-color: #141424; width: 1px; height: 1px; }
QSplitter::handle:hover { background-color: #4d59fb; }

/* ── PROGRESS BAR ────────────────────────────── */

QProgressBar {
    background-color: #1e1e38;
    border: none;
    border-radius: 6px;
    text-align: center;
    font-size: 10px;
    font-weight: 700;
    color: #e8eaf0;
    height: 12px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #4d59fb, stop:1 #6c3aef);
    border-radius: 6px;
}

/* ── QUOTA BANNER ────────────────────────────── */

QFrame#quota_banner {
    background-color: #1a1400;
    border-top: 1px solid #3d3000;
    border-bottom: 1px solid #3d3000;
}
"""


def get_stylesheet() -> str:
    return STYLESHEET