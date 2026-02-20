import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication
from app.desktop.ui.main_window import DesktopApp

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    # Set application metadata
    app.setApplicationName("YT Music Downloader Pro")
    app.setApplicationDisplayName("YT Music Downloader Pro")
    
    window = DesktopApp()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()