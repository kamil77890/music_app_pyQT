"""
Cache ostatnich rekomendacji (lista zapytań wyszukiwania) na dysku.
Unieważnianie przy zmianie folderu biblioteki lub liczby plików audio.
"""
from __future__ import annotations

import json
import os
from typing import List, Optional

from app.desktop.config import CONFIG_FILE

CACHE_VERSION = 1
_CACHE_PATH = CONFIG_FILE.parent / "recommendations_cache.json"

_AUDIO_EXTS = {".mp3", ".m4a", ".mp4", ".flac", ".wav", ".ogg"}


def count_audio_files(download_path: str) -> int:
    """Liczba plików audio w drzewie folderów (do fingerprintu biblioteki)."""
    if not download_path or not os.path.isdir(download_path):
        return 0
    n = 0
    try:
        for root, _, files in os.walk(download_path):
            for f in files:
                if os.path.splitext(f)[1].lower() in _AUDIO_EXTS:
                    n += 1
    except OSError:
        return -1
    return n


def _norm(p: str) -> str:
    try:
        return os.path.normcase(os.path.normpath(os.path.abspath(p)))
    except OSError:
        return p or ""


def try_load_cached_queries(download_path: str) -> Optional[List[str]]:
    """Zwraca listę zapytań z cache lub None, jeśli cache nieaktualny / brak."""
    if not _CACHE_PATH.is_file():
        return None
    try:
        with open(_CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    if data.get("version") != CACHE_VERSION:
        return None
    if _norm(str(data.get("download_path", ""))) != _norm(download_path):
        return None
    cached_count = data.get("library_song_count")
    if not isinstance(cached_count, int) or cached_count < 0:
        return None
    current_count = count_audio_files(download_path)
    if current_count < 0 or current_count != cached_count:
        return None
    queries = data.get("queries")
    if not isinstance(queries, list) or not queries:
        return None
    out = [str(q).strip() for q in queries if str(q).strip()]
    return out if out else None


def save_cached_queries(
    download_path: str,
    queries: List[str],
    library_song_count: int,
) -> None:
    """Zapisuje wynik działania RecommenderThread."""
    if not queries or library_song_count < 0:
        return
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": CACHE_VERSION,
            "download_path": _norm(download_path),
            "library_song_count": library_song_count,
            "queries": list(queries),
        }
        with open(_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
