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
from typing import Dict, List, Optional, Set, Tuple

log = logging.getLogger(__name__)

_AUDIO_EXTS = frozenset({".mp3", ".m4a", ".mp4", ".flac", ".wav", ".ogg"})

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
            log.warning("sync_from_library: metadata module missing, skip")
            return 0

        download_path = os.path.abspath(download_path)
        if not os.path.isdir(download_path):
            log.warning(
                "«All Songs» sync skipped: download_path is not a directory: %s",
                download_path,
            )
            return 0

        self._folder = PlaylistManager.ensure_default_playlist(download_path)
        master = os.path.normpath(self._folder)

        _EXTS = _AUDIO_EXTS
        data = PlaylistManager.get_playlist_info(self._folder)
        initial_json_tracks = len(data.get("songs", []))
        existing = {
            os.path.normcase(os.path.abspath(s.get("file_path", "")))
            for s in data.get("songs", [])
            if s.get("file_path")
        }
        added = 0
        disk_mp3 = 0
        disk_audio = 0
        disk_audio_norm_to_fp: Dict[str, str] = {}

        log.info(
            "«All Songs» scan start: config download_path=%s | «All Songs» dir=%s | "
            "already in playlist.json=%d",
            download_path,
            master,
            initial_json_tracks,
        )

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
                    log.debug("  + added to «All Songs»: %s", fp)
            except Exception as exc:
                log.debug("skip file %s: %s", fp, exc)

        def _visit_audio(fp: str) -> None:
            nonlocal disk_mp3, disk_audio
            ext = os.path.splitext(fp)[1].lower()
            if ext not in _EXTS:
                return
            disk_audio += 1
            if ext == ".mp3":
                disk_mp3 += 1
            try:
                nk = os.path.normcase(os.path.abspath(fp))
                disk_audio_norm_to_fp[nk] = fp
            except OSError:
                pass
            _try_add(fp)

        # 1) Files stored directly under «All Songs» (or nested inside it)
        if os.path.isdir(master):
            for root, _dirs, files in os.walk(master):
                for f in files:
                    _visit_audio(os.path.join(root, f))

        # 2) Files anywhere else under the download root (other playlists, loose files)
        for root, _dirs, files in os.walk(download_path):
            nroot = os.path.normpath(root)
            if nroot.startswith(master):
                continue
            for f in files:
                _visit_audio(os.path.join(root, f))

        # 3) Extra library roots from config (e.g. music-server/app/songs)
        try:
            from app.desktop.config import config as _cfg

            extras = _cfg.get_library_scan_extra_paths()
            if extras:
                log.info("Also scanning library_scan_extra_paths (%d): %s", len(extras), extras)
            for raw in extras:
                extra = os.path.abspath(os.path.expanduser(str(raw).strip()))
                if not extra or not os.path.isdir(extra):
                    log.info("  (skip extra path, missing or not a dir: %s)", raw)
                    continue
                log.info("  scanning extra root: %s", extra)
                for root, _dirs, files in os.walk(extra):
                    for f in files:
                        _visit_audio(os.path.join(root, f))
        except Exception as exc:
            log.warning("extra library scan: %s", exc)

        # Drugi krok: plik jest na dysku, ale nie ma go w JSON (np. zablokowany duplikatem tytuł+artysta).
        data_now = PlaylistManager.get_playlist_info(self._folder)
        json_norms: Set[str] = {
            os.path.normcase(os.path.abspath(s.get("file_path", "")))
            for s in data_now.get("songs", [])
            if s.get("file_path")
        }
        missing_norms: List[Tuple[str, str]] = [
            (nk, disk_audio_norm_to_fp[nk])
            for nk in disk_audio_norm_to_fp
            if nk not in json_norms
        ]
        if missing_norms or initial_json_tracks != len(disk_audio_norm_to_fp):
            log.info(
                "«All Songs» count check: JSON tracks=%d, distinct audio paths on disk=%d, .mp3=%d — "
                "missing in JSON=%d",
                initial_json_tracks,
                len(disk_audio_norm_to_fp),
                disk_mp3,
                len(missing_norms),
            )
        reconcile = 0
        for _nk, fp in missing_norms:
            try:
                if PlaylistManager.add_song_to_playlist(
                    self._folder, fp, dedupe_paths_only=True
                ):
                    reconcile += 1
                    added += 1
                    try:
                        existing.add(os.path.normcase(os.path.abspath(fp)))
                    except OSError:
                        pass
            except Exception as exc:
                log.debug("reconcile skip %s: %s", fp, exc)
        if reconcile:
            log.info(
                "«All Songs» path reconcile: +%d (dedupe tylko po ścieżce — różne pliki z tym samym tagiem)",
                reconcile,
            )

        log.info(
            "«All Songs» scan done: .mp3 on disk=%d, all audio on disk=%d, new rows added=%d",
            disk_mp3,
            disk_audio,
            added,
        )
        return added

    def get_all_songs(self) -> List[Dict]:
        return PlaylistManager.get_playlist_info(self._folder).get("songs", [])

    def get_folder(self) -> str:
        return self._folder


_manager: Optional[AutoPlaylistManager] = None


def count_library_audio_files() -> int:
    """Liczba unikalnych plików audio: główny download_path + library_scan_extra_paths z config."""
    from app.desktop.config import config as _cfg

    roots: List[str] = []
    dp = os.path.abspath(_cfg.get_download_path())
    roots.append(dp)
    for raw in _cfg.get_library_scan_extra_paths():
        ap = os.path.abspath(os.path.expanduser(str(raw).strip()))
        if ap and ap not in roots and os.path.isdir(ap):
            roots.append(ap)

    seen: Set[str] = set()
    n = 0
    for r in roots:
        if not os.path.isdir(r):
            continue
        try:
            for root, _dirs, files in os.walk(r):
                for f in files:
                    if os.path.splitext(f)[1].lower() not in _AUDIO_EXTS:
                        continue
                    fp = os.path.join(root, f)
                    try:
                        k = os.path.normcase(os.path.abspath(fp))
                    except OSError:
                        continue
                    if k in seen:
                        continue
                    seen.add(k)
                    n += 1
        except OSError:
            continue
    return n


def apply_download_to_master_playlist(song_dict: dict, file_path: str) -> int:
    """
    Po udanym pobraniu: dopisz do «All Songs» i wykonaj pełny sync z dysku
    (nowe pliki spoza aplikacji też trafią do playlisty).
    Zwraca liczbę rekordów dodanych przez krok sync (zwykle 0 jeśli add_song wystarczył).
    """
    if not file_path or not os.path.isfile(file_path):
        return 0
    mgr = get_auto_playlist_manager()
    try:
        from app.desktop.utils.metadata import get_audio_metadata

        meta = get_audio_metadata(file_path)
    except Exception:
        meta = {}
    if isinstance(song_dict, dict):
        meta = {**song_dict, **meta}
    mgr.add_song(file_path, meta)
    from app.desktop.config import config

    dp = os.path.abspath(config.get_download_path())
    added = mgr.sync_from_library(dp)
    if added:
        log.info("Post-download sync: +%d file(s) in «All Songs»", added)
    log.info("Added to master playlist: %s", meta.get("title", file_path))
    return added


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
    """Slot for DownloadThread.song_complete — dodaje utwór i robi sync biblioteki z dysku."""
    if success and file_path and os.path.exists(file_path):
        apply_download_to_master_playlist(song_dict, file_path)


# Backwards compatibility for imports
MASTER_NAME = DEFAULT_PLAYLIST_NAME
__all__ = [
    "AutoPlaylistManager",
    "get_auto_playlist_manager",
    "auto_playlist_slot",
    "apply_download_to_master_playlist",
    "count_library_audio_files",
    "MASTER_NAME",
    "LEGACY_AUTO_PLAYLIST_FOLDER",
]
