from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QCheckBox, QSlider, QSpinBox,
    QGroupBox, QFormLayout, QWidget
)
from PyQt5.QtCore import Qt
import app.desktop.config as config_module


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = config_module.config
        self.setWindowTitle("Settings")
        self.setFixedSize(560, 520)
        self.setProperty("dialog", "settings")
        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        title = QLabel("⚙️ Settings")
        title.setProperty("title", "true")
        title.setObjectName("settingsTitle")
        root.addWidget(title)

        download_group = QGroupBox("Download")
        form = QFormLayout(download_group)
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFormAlignment(Qt.AlignLeft)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        self.path_input = QLineEdit()
        self.browse_btn = QPushButton("Browse")
        self.browse_btn.setProperty("icon", "true")
        self.browse_btn.clicked.connect(self.browse_path)
        row = QWidget()
        row_l = QHBoxLayout(row)
        row_l.setContentsMargins(0, 0, 0, 0)
        row_l.addWidget(self.path_input)
        row_l.addWidget(self.browse_btn)
        form.addRow("Download path:", row)

        self.concurrent_spin = QSpinBox()
        self.concurrent_spin.setRange(1, 10)
        self.concurrent_spin.setFixedWidth(120)
        form.addRow("Concurrent downloads:", self.concurrent_spin)

        self.auto_download = QCheckBox("Auto-download after preview")
        form.addRow("", self.auto_download)

        root.addWidget(download_group)

        player_group = QGroupBox("Player")
        pform = QFormLayout(player_group)
        pform.setLabelAlignment(Qt.AlignLeft)
        pform.setHorizontalSpacing(12)
        pform.setVerticalSpacing(10)

        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_label = QLabel("70%")
        vol_widget = QWidget()
        vol_row = QHBoxLayout(vol_widget)
        vol_row.setContentsMargins(0, 0, 0, 0)
        vol_row.addWidget(self.volume_slider)
        vol_row.addWidget(self.volume_label)
        pform.addRow("Volume:", vol_widget)

        self.loop_checkbox = QCheckBox("Repeat current track")
        pform.addRow("", self.loop_checkbox)

        self.autoplay_checkbox = QCheckBox("Auto-play next")
        pform.addRow("", self.autoplay_checkbox)

        root.addWidget(player_group)

        metadata_group = QGroupBox("Metadata")
        mform = QFormLayout(metadata_group)
        mform.setLabelAlignment(Qt.AlignLeft)
        mform.setHorizontalSpacing(12)
        mform.setVerticalSpacing(10)

        self.hide_metadata_popup = QCheckBox("Don't show metadata problem notifications")
        mform.addRow("", self.hide_metadata_popup)

        root.addWidget(metadata_group)

        root.addStretch()

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.save_btn = QPushButton("Save")
        self.save_btn.setProperty("style", "primary")
        self.save_btn.clicked.connect(self.save_settings)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setProperty("nav", "true")
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.save_btn)
        btn_row.addWidget(self.cancel_btn)
        root.addLayout(btn_row)

        self.volume_slider.valueChanged.connect(lambda v: self.volume_label.setText(f"{v}%"))

    def load_settings(self):
        self.path_input.setText(self.config.get("download_path"))
        self.volume_slider.setValue(self.config.get("volume", 70))
        self.volume_label.setText(f"{self.config.get('volume', 70)}%")
        self.loop_checkbox.setChecked(self.config.get("loop_enabled", True))
        self.autoplay_checkbox.setChecked(self.config.get("autoplay_enabled", True))
        self.auto_download.setChecked(self.config.get("auto_download", False))
        self.concurrent_spin.setValue(self.config.get("concurrent_downloads", 3))
        self.hide_metadata_popup.setChecked(self.config.get("ignore_metadata_fix", False))

    def browse_path(self):
        p = QFileDialog.getExistingDirectory(self, "Select download folder", self.path_input.text() or ".")
        if p:
            self.path_input.setText(p)

    def save_settings(self):
        self.config.set("download_path", self.path_input.text())
        self.config.set("volume", self.volume_slider.value())
        self.config.set("loop_enabled", self.loop_checkbox.isChecked())
        self.config.set("autoplay_enabled", self.autoplay_checkbox.isChecked())
        self.config.set("auto_download", self.auto_download.isChecked())
        self.config.set("concurrent_downloads", self.concurrent_spin.value())
        self.config.set("ignore_metadata_fix", self.hide_metadata_popup.isChecked())
        self.accept()



def get_stylesheet():
    return r"""
    QMainWindow, QWidget, QDialog {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 #071028, stop:0.5 #0f1b34, stop:1 #071028);
        color: #e9eefb;
        font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
        font-size: 13px;
        font-weight: 400;
    }
    QLabel[title="true"]#settingsTitle {
        color: #ffffff;
        font-size: 18px;
        font-weight: 800;
        padding: 6px 0 12px 2px;
        letter-spacing: -0.2px;
    }
    QDialog[dialog="settings"] {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 rgba(12, 17, 32, 0.95), stop:1 rgba(18, 28, 48, 0.95));
        border: 1px solid rgba(138, 43, 226, 0.28);
        border-radius: 14px;
    }
    QGroupBox {
        background: rgba(255,255,255,0.03);
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 10px;
        margin-top: 12px;
        padding: 12px;
        color: #d6dff6;
        font-weight: 700;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 6px;
        color: #b7bff0;
        font-size: 12px;
        letter-spacing: 0.2px;
    }
    QFormLayout QLabel {
        color: #9fb0d9;
        font-size: 13px;
        font-weight: 600;
    }
    QLineEdit, QSpinBox, QComboBox {
        background: rgba(255,255,255,0.035);
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 10px;
        padding: 8px 12px;
        color: #eaf0ff;
        min-height: 36px;
        selection-background-color: rgba(138, 43, 226, 0.45);
    }
    QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
        border: 1px solid rgba(138,43,226,0.6);
        background: rgba(255,255,255,0.05);
        outline: none;
        box-shadow: 0 4px 18px rgba(11, 8, 36, 0.55);
    }
    QLineEdit::placeholder {
        color: #7486a6;
        font-style: italic;
    }
    QSlider::groove:horizontal {
        background: rgba(255,255,255,0.06);
        height: 6px;
        border-radius: 6px;
    }
    QSlider::handle:horizontal {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #cbb9ff, stop:1 #8b5cf6);
        width: 18px; height: 18px; margin: -6px 0; border-radius: 9px; border: 2px solid rgba(0,0,0,0.25);
    }
    QSlider::sub-page:horizontal { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #8b5cf6, stop:1 #06b6d4); border-radius: 6px; }
    QCheckBox { color: #c6d6f5; font-size: 13px; spacing: 10px; }
    QCheckBox::indicator { width: 18px; height: 18px; border-radius: 4px; border:1px solid rgba(255,255,255,0.08); background: rgba(0,0,0,0.18); }
    QCheckBox::indicator:checked { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #8b5cf6, stop:1 #06b6d4); border: none; }
    QPushButton {
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 10px;
        padding: 8px 14px;
        color: #eaf0ff;
        min-height: 38px;
        font-weight: 700;
    }
    QPushButton:hover { background: rgba(138,43,226,0.18); }
    QPushButton:pressed { background: rgba(138,43,226,0.26); }
    QPushButton[style="primary"] {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #8b5cf6, stop:1 #06b6d4);
        color: #ffffff; border: none; padding: 10px 18px; min-width: 110px;
        box-shadow: 0 6px 20px rgba(11,8,36,0.55);
    }
    QPushButton[style="primary"]:hover { opacity: 0.95; }
    QPushButton[nav="true"] { background: transparent; border: 1px solid rgba(255,255,255,0.06); color: #bcd1ff; }
    QPushButton[icon="true"] {
        min-width: 44px; min-height: 36px; max-width: 44px; padding: 6px; font-size: 13px;
        background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06);
    }
    QWidget { background: transparent; }
    QScrollBar:vertical { background: rgba(255,255,255,0.02); width:10px; }
    QScrollBar::handle:vertical { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #8b5cf6, stop:1 #06b6d4); border-radius:6px; }
    QToolTip { background: rgba(8,12,28,0.95); border: 1px solid rgba(138,43,226,0.45); color: #eaf0ff; padding: 6px 10px; border-radius:6px; }
    """