"""
Thread for loading thumbnails safely with proper cleanup.
Emits the **full-resolution** pixmap so widgets can scale to their layout (no fixed 78px).
"""

import requests
from PyQt5.QtCore import QThread, pyqtSignal, QMutex
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt


# Max dimension to limit RAM; still plenty for crisp UI scaling
_MAX_SIDE = 1024


class ThumbnailLoader(QThread):
    """Download an image URL and emit a QPixmap (not pre-cropped to a tiny size)."""

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

            if self._stop_flag:
                return

            response = requests.get(self.url, timeout=15)

            if self._stop_flag:
                return

            if response.status_code == 200:
                pixmap = QPixmap()
                pixmap.loadFromData(response.content)

                if self._stop_flag:
                    return

                if not pixmap.isNull():
                    w, h = pixmap.width(), pixmap.height()
                    if max(w, h) > _MAX_SIDE:
                        pixmap = pixmap.scaled(
                            _MAX_SIDE,
                            _MAX_SIDE,
                            Qt.KeepAspectRatio,
                            Qt.SmoothTransformation,
                        )
                    if not self._stop_flag:
                        self.loaded.emit(pixmap)
                    return

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

    def stop(self):
        self._mutex.lock()
        self._stop_flag = True
        was_running = self._is_running
        self._mutex.unlock()

        if was_running and self.isRunning():
            self.quit()
            self.wait(500)
