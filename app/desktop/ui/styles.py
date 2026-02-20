def get_stylesheet():
    """Return the redesigned application stylesheet"""
    return """
    /* ===== GLOBAL STYLES ===== */
    QMainWindow, QWidget, QDialog {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 #0a0e27, stop:0.5 #16213e, stop:1 #0a0e27);
        color: #e4e9f7;
        font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
        font-size: 13px;
        font-weight: 400;
    }
    
    /* ===== TOP BAR ===== */
    QFrame[topbar="true"] {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 rgba(139, 92, 246, 0.4), 
            stop:0.5 rgba(6, 182, 212, 0.3), 
            stop:1 rgba(139, 92, 246, 0.4));
        border: none;
        border-bottom: 2px solid rgba(138, 43, 226, 0.5);
        border-radius: 0;
    }
    
    /* ===== GLASS PANELS ===== */
    QFrame[glass="true"] {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 rgba(255, 255, 255, 0.08),
            stop:1 rgba(255, 255, 255, 0.04));
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: 16px;
    }
    
    QFrame[glass_header="true"] {
        background: rgba(255, 255, 255, 0.05);
        border: none;
        border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 0;
        border-top-left-radius: 16px;
        border-top-right-radius: 16px;
    }
    
    /* ===== TITLES ===== */
    QLabel {
        color: #e4e9f7;
        background: transparent;
    }
    
    QLabel[title="hero"] {
        color: #ffffff;
        font-size: 32px;
        font-weight: 700;
        letter-spacing: -0.5px;
        background: transparent;
    }
    
    QLabel[title="large"] {
        color: #ffffff;
        font-size: 24px;
        font-weight: 700;
        letter-spacing: -0.3px;
        background: transparent;
    }
    
    QLabel[title="medium"] {
        color: #e4e9f7;
        font-size: 18px;
        font-weight: 600;
        background: transparent;
    }
    
    QLabel[title="small"] {
        color: #b8c5d6;
        font-size: 12px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 1px;
        background: transparent;
    }
    
    QLabel[subtitle="true"] {
        color: #8a9bb0;
        font-size: 14px;
        font-weight: 400;
        background: transparent;
    }
    
    /* ===== BUTTONS ===== */
    QPushButton {
        background: rgba(255, 255, 255, 0.08);
        border: 1px solid rgba(255, 255, 255, 0.15);
        border-radius: 10px;
        padding: 10px 20px;
        color: #e4e9f7;
        font-size: 13px;
        font-weight: 600;
        min-height: 40px;
    }
    
    QPushButton:hover {
        background: rgba(138, 43, 226, 0.25);
        border: 1px solid rgba(138, 43, 226, 0.5);
    }
    
    QPushButton:pressed {
        background: rgba(138, 43, 226, 0.4);
    }
    
    QPushButton:disabled {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.08);
        color: #4a5568;
    }
    
    /* ===== GRADIENT BUTTONS ===== */
    QPushButton[style="primary"] {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #8b5cf6, stop:0.5 #06b6d4, stop:1 #8b5cf6);
        border: none;
        color: white;
        font-weight: 700;
        padding: 12px 24px;
        min-height: 44px;
    }
    
    QPushButton[style="primary"]:hover {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #a78bfa, stop:0.5 #22d3ee, stop:1 #a78bfa);
    }
    
    QPushButton[style="primary"]:pressed {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #7c3aed, stop:0.5 #0891b2, stop:1 #7c3aed);
    }
    
    /* ===== NAV BUTTONS ===== */
    QPushButton[nav="true"] {
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 10px;
        padding: 10px 20px;
        color: #b8c5d6;
        font-size: 13px;
        font-weight: 600;
        min-height: 42px;
        min-width: 120px;
    }
    
    QPushButton[nav="true"]:hover {
        background: rgba(255, 255, 255, 0.1);
        border: 1px solid rgba(138, 43, 226, 0.3);
    }
    
    QPushButton[nav="active"] {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 rgba(139, 92, 246, 0.4),
            stop:1 rgba(6, 182, 212, 0.3));
        border: 1px solid rgba(138, 43, 226, 0.5);
        color: white;
        font-weight: 700;
    }
    
    /* ===== ICON BUTTONS ===== */
    QPushButton[icon="true"] {
        background: rgba(255, 255, 255, 0.08);
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: 10px;
        padding: 10px;
        min-width: 44px;
        min-height: 44px;
        max-width: 44px;
        max-height: 44px;
        font-size: 18px;
    }
    
    QPushButton[icon="true"]:hover {
        background: rgba(138, 43, 226, 0.25);
        border: 1px solid rgba(138, 43, 226, 0.5);
    }
    
    /* ===== INPUT FIELDS ===== */
    QLineEdit {
        background: rgba(255, 255, 255, 0.06);
        border: 2px solid rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        padding: 12px 16px;
        color: #ffffff;
        font-size: 14px;
        selection-background-color: rgba(138, 43, 226, 0.5);
        selection-color: white;
    }
    
    QLineEdit:focus {
        background: rgba(255, 255, 255, 0.08);
        border: 2px solid rgba(138, 43, 226, 0.6);
    }
    
    QLineEdit:hover {
        border: 2px solid rgba(255, 255, 255, 0.2);
    }
    
    QLineEdit::placeholder {
        color: #6b7280;
        font-style: italic;
    }
    
    QLineEdit[search="true"] {
        background: transparent;
        border: none;
        font-size: 16px;
        padding: 8px 16px;
    }
    
    /* ===== SCROLLBARS ===== */
    QScrollBar:vertical {
        background: rgba(255, 255, 255, 0.03);
        width: 10px;
        border-radius: 5px;
        margin: 0;
    }
    
    QScrollBar::handle:vertical {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #8b5cf6, stop:1 #06b6d4);
        border-radius: 5px;
        min-height: 30px;
    }
    
    QScrollBar::handle:vertical:hover {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #a78bfa, stop:1 #22d3ee);
    }
    
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }
    
    QScrollBar:horizontal {
        background: rgba(255, 255, 255, 0.03);
        height: 10px;
        border-radius: 5px;
    }
    
    QScrollBar::handle:horizontal {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #8b5cf6, stop:1 #06b6d4);
        border-radius: 5px;
        min-width: 30px;
    }
    
    /* ===== SONG CARDS ===== */
    SongCard {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 rgba(255, 255, 255, 0.08),
            stop:1 rgba(255, 255, 255, 0.04));
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: 12px;
    }
    
    SongCard:hover {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 rgba(138, 43, 226, 0.2),
            stop:1 rgba(6, 182, 212, 0.15));
        border: 1px solid rgba(138, 43, 226, 0.4);
    }
    
    /* ===== TREE & LIST ===== */
    QTreeWidget, QListWidget {
        background: transparent;
        border: none;
        outline: none;
    }
    
    QTreeWidget::item, QListWidget::item {
        padding: 10px 14px;
        border-radius: 8px;
        color: #b8c5d6;
        margin: 2px 4px;
    }
    
    QTreeWidget::item:selected, QListWidget::item:selected {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 rgba(139, 92, 246, 0.4),
            stop:1 rgba(6, 182, 212, 0.3));
        color: white;
        font-weight: 600;
    }
    
    QTreeWidget::item:hover:!selected, QListWidget::item:hover:!selected {
        background: rgba(255, 255, 255, 0.08);
    }
    
    /* ===== PROGRESS BARS ===== */
    QProgressBar {
        background: rgba(255, 255, 255, 0.08);
        border: none;
        border-radius: 8px;
        text-align: center;
        font-size: 11px;
        font-weight: 600;
        color: #e4e9f7;
        height: 20px;
    }
    
    QProgressBar::chunk {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #8b5cf6, stop:0.5 #06b6d4, stop:1 #8b5cf6);
        border-radius: 8px;
    }
    
    /* ===== SLIDERS ===== */
    QSlider::groove:horizontal {
        background: rgba(255, 255, 255, 0.1);
        height: 6px;
        border-radius: 3px;
    }
    
    QSlider::handle:horizontal {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #a78bfa, stop:1 #8b5cf6);
        width: 18px;
        height: 18px;
        margin: -6px 0;
        border-radius: 9px;
        border: 2px solid rgba(255, 255, 255, 0.3);
    }
    
    QSlider::handle:horizontal:hover {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #c4b5fd, stop:1 #a78bfa);
    }
    
    QSlider::sub-page:horizontal {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #8b5cf6, stop:1 #06b6d4);
        border-radius: 3px;
    }
    
    /* ===== CHECKBOXES ===== */
    QCheckBox {
        color: #b8c5d6;
        font-size: 13px;
        spacing: 10px;
    }
    
    QCheckBox::indicator {
        width: 20px;
        height: 20px;
        border: 2px solid rgba(138, 43, 226, 0.5);
        border-radius: 5px;
        background: rgba(255, 255, 255, 0.05);
    }
    
    QCheckBox::indicator:checked {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 #8b5cf6, stop:1 #06b6d4);
        border-color: transparent;
    }
    
    QCheckBox::indicator:hover {
        border-color: rgba(138, 43, 226, 0.8);
    }
    
    /* ===== MENUS ===== */
    QMenu {
        background: rgba(22, 33, 62, 0.95);
        border: 1px solid rgba(138, 43, 226, 0.4);
        border-radius: 10px;
        padding: 6px;
    }
    
    QMenu::item {
        padding: 10px 36px 10px 16px;
        border-radius: 6px;
        color: #b8c5d6;
        margin: 2px;
    }
    
    QMenu::item:selected {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 rgba(139, 92, 246, 0.3),
            stop:1 rgba(6, 182, 212, 0.2));
        color: white;
    }
    
    QMenu::separator {
        height: 1px;
        background: rgba(255, 255, 255, 0.1);
        margin: 6px 10px;
    }
    
    /* ===== TOOLTIPS ===== */
    QToolTip {
        background: rgba(16, 23, 48, 0.95);
        border: 1px solid rgba(138, 43, 226, 0.5);
        border-radius: 8px;
        color: #e4e9f7;
        padding: 8px 12px;
        font-size: 12px;
    }
    
    /* ===== DIALOGS ===== */
    QDialog {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 #0f1729, stop:1 #1a2332);
        border: 1px solid rgba(138, 43, 226, 0.4);
        border-radius: 16px;
    }
    
    /* ===== GROUP BOXES ===== */
    QGroupBox {
        color: #8b5cf6;
        font-weight: 600;
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 10px;
        margin-top: 16px;
        padding-top: 16px;
        background: rgba(255, 255, 255, 0.04);
    }
    
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 14px;
        padding: 0 10px;
    }
    
    /* ===== AUDIO PLAYER ===== */
    AudioPlayerWidget {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 rgba(10, 14, 39, 0.95),
            stop:1 rgba(22, 33, 62, 0.95));
        border-top: 2px solid rgba(138, 43, 226, 0.5);
        border-radius: 0;
    }
    
    QPushButton[player="true"] {
        background: rgba(255, 255, 255, 0.08);
        border: 1px solid rgba(255, 255, 255, 0.15);
        border-radius: 10px;
        padding: 10px;
        color: #e4e9f7;
        font-size: 16px;
        min-width: 44px;
        min-height: 44px;
    }
    
    QPushButton[player="true"]:hover {
        background: rgba(138, 43, 226, 0.3);
        border: 1px solid rgba(138, 43, 226, 0.6);
    }
    
    QPushButton[player="play"] {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #8b5cf6, stop:1 #06b6d4);
        border: none;
        border-radius: 26px;
        color: white;
        font-size: 18px;
        min-width: 52px;
        min-height: 52px;
    }
    
    QPushButton[player="play"]:hover {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #a78bfa, stop:1 #22d3ee);
    }
    
    /* ===== SPLITTER ===== */
    QSplitter::handle {
        background: rgba(138, 43, 226, 0.2);
        width: 2px;
    }
    
    QSplitter::handle:hover {
        background: rgba(138, 43, 226, 0.5);
    }
    
    /* ===== STATUS BAR ===== */
    QFrame[statusbar="true"] {
        background: rgba(10, 14, 39, 0.8);
        border-top: 1px solid rgba(255, 255, 255, 0.1);
    }
    
    /* ===== DOWNLOAD ITEM ===== */
    DownloadManagerItem {
        background: rgba(255, 255, 255, 0.06);
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: 10px;
    }
    
    /* ===== TABS ===== */
    QTabWidget::pane {
        border: none;
        background: transparent;
    }
    
    QTabBar::tab {
        background: rgba(255, 255, 255, 0.05);
        color: #8a9bb0;
        padding: 12px 24px;
        margin-right: 4px;
        border-top-left-radius: 10px;
        border-top-right-radius: 10px;
        font-size: 13px;
        font-weight: 600;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-bottom: none;
    }
    
    QTabBar::tab:selected {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 rgba(139, 92, 246, 0.3),
            stop:1 rgba(6, 182, 212, 0.2));
        color: white;
        border: 1px solid rgba(138, 43, 226, 0.4);
        border-bottom: none;
    }
    
    QTabBar::tab:hover:!selected {
        background: rgba(255, 255, 255, 0.08);
    }
    """
