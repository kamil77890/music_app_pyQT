"""
Thread for downloading songs — with pause / stop support
"""

import logging
import os
from PyQt5.QtCore import QThread, pyqtSignal, QMutex, QMutexLocker

log = logging.getLogger(__name__)

from app.desktop.utils.helpers import song_to_dict, get_field, clean_filename, clean_video_id
from app.desktop.utils.metadata import get_mp3_metadata
from app.desktop.logic.download_manager import DownloadManager
from app.logic.ultimate_downloader import download_song


class DownloadThread(QThread):
    """Thread for downloading songs"""

    # ── signals ────────────────────────────────────────────────
    # progress(percent 0-100, title, current_index, total)
    progress      = pyqtSignal(int, str, int, int)
    # song_complete(song_dict, success, file_path, error_msg)
    song_complete  = pyqtSignal(dict, bool, str, str)
    # finished(downloaded_file_paths)
    finished       = pyqtSignal(list)
    error          = pyqtSignal(str, object)

    def __init__(self, songs, download_path):
        super().__init__()
        self.songs           = list(songs)
        self.download_path   = download_path
        self.download_manager = DownloadManager(download_path)
        self._mutex          = QMutex()
        self._stop_flag      = False
        self._paused         = False
        self._removed        = set()   # indices to skip

    # ── control API ────────────────────────────────────────────

    def stop(self):
        with QMutexLocker(self._mutex):
            self._stop_flag = True
            self._paused    = False

    def pause(self):
        with QMutexLocker(self._mutex):
            self._paused = True

    def resume(self):
        with QMutexLocker(self._mutex):
            self._paused = False

    def remove_song(self, index: int):
        """Mark a song index to be skipped (only effective before it starts)."""
        with QMutexLocker(self._mutex):
            self._removed.add(index)

    # ── run ────────────────────────────────────────────────────

    def run(self):
        downloaded = []
        total = len(self.songs)

        for i, song in enumerate(self.songs):

            # ── wait while paused ──
            while True:
                with QMutexLocker(self._mutex):
                    if self._stop_flag or not self._paused:
                        break
                self.msleep(200)

            # ── check stop / skip ──
            with QMutexLocker(self._mutex):
                if self._stop_flag:
                    break
                if i in self._removed:
                    continue

            song_dict = {}
            try:
                song_dict = song_to_dict(song)

                # extract video ID
                video_id = None
                for field in ["videoId", "id", "url"]:
                    video_id = get_field(song_dict, field)
                    if video_id:
                        break

                title  = get_field(song_dict, "title",  "Unknown")
                artist = get_field(song_dict, "artist", "Unknown Artist")

                if not video_id:
                    log.warning("No video ID: %s", title)
                    self.song_complete.emit(song_dict, False, "", "No video ID found")
                    continue

                video_id = clean_video_id(video_id)
                if not video_id:
                    log.warning("Invalid video ID: %s", title)
                    self.song_complete.emit(song_dict, False, "", "Invalid video ID")
                    continue

                log.info("Downloading %d/%d: %s - %s", i + 1, total, title, artist)

                safe_title  = clean_filename(title)
                safe_artist = clean_filename(artist)

                path = download_song(video_id, safe_title, format_ext="mp3")

                if path and os.path.exists(path):
                    # rename to "Artist - Title.mp3"
                    target_name = f"{safe_artist} - {safe_title}.mp3"
                    target_path = os.path.join(os.path.dirname(path), target_name)
                    if os.path.basename(path) != target_name:
                        try:
                            if os.path.exists(target_path):
                                os.remove(target_path)
                            os.rename(path, target_path)
                            path = target_path
                        except Exception as e:
                            log.error("Rename failed: %s", e)

                    downloaded.append(path)
                    self.progress.emit(100, title, i + 1, total)
                    self.song_complete.emit(song_dict, True, path, "")
                    self.download_manager.create_song_link(path, video_id, title, artist)
                else:
                    log.error("Download failed: %s", title)
                    self.progress.emit(100, title, i + 1, total)
                    self.song_complete.emit(song_dict, False, "", "Download failed")

            except Exception as e:
                err = str(e)
                log.exception("Download error: %s", err)
                self.progress.emit(100,
                    get_field(song_dict, "title", "Unknown"), i + 1, total)
                self.song_complete.emit(song_dict, False, "", err)
                self.error.emit(err, song_dict)

        self.finished.emit(downloaded)