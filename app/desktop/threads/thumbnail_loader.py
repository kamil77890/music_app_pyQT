"""
Thread for loading thumbnails safely with proper cleanup
"""

import requests
from PyQt5.QtCore import QThread, pyqtSignal, QMutex, QWaitCondition
from PyQt5.QtGui import QPixmap, QPainter, QPen, QColor, QFont, QPainterPath
from PyQt5.QtCore import Qt
import time


class ThumbnailLoader(QThread):
    """Thread for loading thumbnails safely with proper cleanup"""
    loaded = pyqtSignal(QPixmap)
    error = pyqtSignal()
    
    def __init__(self, url: str):
        super().__init__()
        self.url = url
        self._is_running = False
        self._mutex = QMutex()
        self._stop_flag = False
        
    def run(self):
        try:
            self._mutex.lock()
            self._is_running = True
            self._mutex.unlock()
            
            # Check if we should stop before starting
            if self._stop_flag:
                return
            
            # Download image with timeout
            response = requests.get(self.url, timeout=10)
            
            # Check if we should stop during download
            if self._stop_flag:
                return
                
            if response.status_code == 200:
                # Create pixmap in this thread
                pixmap = QPixmap()
                pixmap.loadFromData(response.content)
                
                # Check if we should stop before processing
                if self._stop_flag:
                    return
                
                if not pixmap.isNull():
                    # Create rounded version safely
                    rounded = self.create_rounded_pixmap(pixmap)
                    
                    # Check if we should stop before emitting
                    if not self._stop_flag:
                        self.loaded.emit(rounded)
                    return
            
            # If we get here, something failed
            if not self._stop_flag:
                self.error.emit()
            
        except requests.exceptions.Timeout:
            if not self._stop_flag:
                self.error.emit()
        except Exception:
            if not self._stop_flag:
                self.error.emit()
        finally:
            self._mutex.lock()
            self._is_running = False
            self._mutex.unlock()
    
    def create_rounded_pixmap(self, pixmap: QPixmap) -> QPixmap:
        """Create a rounded pixmap"""
        size = 78
        rounded = QPixmap(size, size)
        rounded.fill(Qt.transparent)
        
        # Paint in this thread
        painter = QPainter(rounded)
        if painter.isActive():
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            
            # Create clipping path
            path = QPainterPath()
            path.addRoundedRect(0, 0, size, size, 6, 6)
            painter.setClipPath(path)
            
            # Scale and draw
            scaled = pixmap.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            painter.drawPixmap(0, 0, scaled)
            painter.end()
        
        return rounded
    
    def stop(self):
        """Safely stop the thumbnail loader"""
        self._mutex.lock()
        self._stop_flag = True
        was_running = self._is_running
        self._mutex.unlock()
        
        if was_running and self.isRunning():
            self.quit()
            self.wait(500)  # Wait up to 500ms for thread to finish