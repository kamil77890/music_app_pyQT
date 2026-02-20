
import os
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtCore import QFile

class AssetManager:
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.assets_dir = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), 
                "assets"
            )
        return cls._instance
    
    def get_icon_path(self, icon_name):
        return os.path.join(self.assets_dir, "icons", icon_name)
    
    def load_icon(self, icon_name, fallback_text=""):
        icon_path = self.get_icon_path(icon_name)
        if os.path.exists(icon_path):
            return QIcon(icon_path)
        elif fallback_text:

            from PyQt5.QtGui import QPainter, QPen, QColor, QFont
            from PyQt5.QtCore import Qt

            pixmap = QPixmap(32, 32)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            if painter.isActive():
                painter.setFont(QFont("Arial", 16))
                painter.setPen(QPen(Qt.white))
                painter.drawText(pixmap.rect(), Qt.AlignCenter, fallback_text)
                painter.end()
            return QIcon(pixmap)
        return QIcon()
    
    def load_pixmap(self, relative_path):
        full_path = os.path.join(self.assets_dir, relative_path)
        if os.path.exists(full_path):
            return QPixmap(full_path)
        return QPixmap()

assets = AssetManager()