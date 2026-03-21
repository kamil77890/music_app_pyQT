"""
auto_playlist.py — master «All Songs» playlist
────────────────────────────────────────────
Every successful download is added to the default playlist
(`PlaylistManager.ensure_default_playlist` → «All Songs»).

Also used by sync_from_library to backfill any audio under the download tree.
"""
from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

from app.desktop.utils.playlist_manager import (
    DEFAULT_PLAYLIST_NAME,
    LEGACY_AUTO_PLAYLIST_FOLDER,
    PlaylistManager,
)


class AutoPlaylistManager:
    """
    Thin wrapper: all writes go through PlaylistManager on the «All Songs» folder.
    """

    def __init__(self, download_path: str):
        self._download_path = os.path.abspath(download_path)
        self._folder = PlaylistManager.ensure_default_playlist(self._download_path)

    def add_song(self, file_path: str, metadata: dict) -> bool:
        """Append song to master playlist (idempotent)."""
        try:
            ok = PlaylistManager.add_song_to_playlist(
                self._folder, file_path, metadata
            )
            return bool(ok)
        except Exception as exc:
            log.error("add_song error: %s", exc)
            return False

    def sync_from_library(self, download_path: str) -> int:
        """
        Walk the library tree and add any audio files not yet in «All Songs» playlist.json.

        Includes files **inside** the «All Songs» folder (flat MP3s like …/songs/All Songs/*.mp3)
        and files in other playlist subfolders — previously the whole «All Songs» tree was skipped.
        """
        try:
            from app.desktop.utils.metadata import get_audio_metadata
        except ImportError:
            return 0

        download_path = os.path.abspath(download_path)
        self._folder = PlaylistManager.ensure_default_playlist(download_path)
        master = os.path.normpath(self._folder)

        _EXTS = {".mp3", ".m4a", ".mp4", ".flac", ".wav", ".ogg"}
        data = PlaylistManager.get_playlist_info(self._folder)
        existing = {
            os.path.normcase(os.path.abspath(s.get("file_path", "")))
            for s in data.get("songs", [])
            if s.get("file_path")
        }
        added = 0

        def _try_add(fp: str) -> None:
            nonlocal added
            try:
                k = os.path.normcase(os.path.abspath(fp))
            except OSError:
                return
            if k in existing:
                return
            try:
                meta = get_audio_metadata(fp)
                if PlaylistManager.add_song_to_playlist(self._folder, fp, meta):
                    existing.add(k)
                    added += 1
            except Exception:
                pass

        # 1) Files stored directly under «All Songs» (or nested inside it)
        if os.path.isdir(master):
            for root, _dirs, files in os.walk(master):
                for f in files:
                    if os.path.splitext(f)[1].lower() not in _EXTS:
                        continue
                    _try_add(os.path.join(root, f))

        # 2) Files anywhere else under the download root (other playlists, loose files)
        for root, _dirs, files in os.walk(download_path):
            nroot = os.path.normpath(root)
            if nroot.startswith(master):
                continue
            for f in files:
                if os.path.splitext(f)[1].lower() not in _EXTS:
                    continue
                _try_add(os.path.join(root, f))

        return added

    def get_all_songs(self) -> List[Dict]:
        return PlaylistManager.get_playlist_info(self._folder).get("songs", [])

    def get_folder(self) -> str:
        return self._folder


_manager: Optional[AutoPlaylistManager] = None


def get_auto_playlist_manager(download_path: str = "") -> AutoPlaylistManager:
    global _manager
    if not download_path:
        from app.desktop.config import config

        download_path = config.get_download_path()
    download_path = os.path.abspath(download_path)
    if _manager is None or getattr(_manager, "_download_path", "") != download_path:
        _manager = AutoPlaylistManager(download_path)
    return _manager


def auto_playlist_slot(song_dict: dict, success: bool, file_path: str, error: str):
    """Slot for DownloadThread.song_complete — adds each finished file to «All Songs»."""
    if success and file_path and os.path.exists(file_path):
        mgr = get_auto_playlist_manager()
        try:
            from app.desktop.utils.metadata import get_audio_metadata

            meta = get_audio_metadata(file_path)
        except Exception:
            meta = {}
        if isinstance(song_dict, dict):
            meta = {**song_dict, **meta}
        mgr.add_song(file_path, meta)
        log.info("Added %s", meta.get("title", file_path))


# Backwards compatibility for imports
MASTER_NAME = DEFAULT_PLAYLIST_NAME
__all__ = [
    "AutoPlaylistManager",
    "get_auto_playlist_manager",
    "auto_playlist_slot",
    "MASTER_NAME",
    "LEGACY_AUTO_PLAYLIST_FOLDER",
]
