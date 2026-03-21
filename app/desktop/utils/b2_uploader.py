"""
Desktop: triggers B2 upload on the FastAPI server (`POST /cloud/upload`).
Upload logic lives in `app/logic/b2_storage.py` and `app/endpoints/cloud.py`.
"""

from __future__ import annotations

import json
import os
from typing import List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PyQt5.QtCore import QThread, pyqtSignal

from app.desktop.config import config


def collect_music_files(directory: str) -> List[str]:
    """Recursive audio file list (for UI counts before upload)."""
    _AUDIO_EXTS = {".mp3", ".m4a", ".mp4", ".flac", ".wav", ".ogg"}
    files = []
    for root, _, filenames in os.walk(directory):
        for f in filenames:
            if os.path.splitext(f)[1].lower() in _AUDIO_EXTS:
                files.append(os.path.join(root, f))
    return sorted(files)


def _api_base() -> str:
    return str(config.get("api_base_url", "http://127.0.0.1:8001")).rstrip("/")


class B2UploadThread(QThread):
    """Calls server `POST /cloud/upload` (non-blocking UI thread)."""

    progress = pyqtSignal(int, int, str)
    file_done = pyqtSignal(str, bool, str)
    upload_finished = pyqtSignal(int, int)

    def __init__(self, music_dir: str, parent=None):
        super().__init__(parent)
        self._music_dir = music_dir

    def run(self):
        body = json.dumps({"directory": os.path.abspath(self._music_dir)}).encode(
            "utf-8"
        )
        req = Request(
            f"{_api_base()}/cloud/upload",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=86400) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            up = int(data.get("uploaded", 0))
            fail = int(data.get("failed", 0))
            self.progress.emit(up + fail, max(up + fail, 1), "done")
            self.file_done.emit("", True, "Server upload finished")
            self.upload_finished.emit(up, fail)
        except HTTPError as e:
            self.file_done.emit("", False, f"HTTP {e.code}: {e.reason}")
            self.upload_finished.emit(0, 0)
        except URLError as e:
            self.file_done.emit("", False, f"Server unreachable: {e.reason}")
            self.upload_finished.emit(0, 0)
        except Exception as exc:
            self.file_done.emit("", False, str(exc))
            self.upload_finished.emit(0, 0)
