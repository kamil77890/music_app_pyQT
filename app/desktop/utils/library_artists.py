"""
Derive "Daily Artists" from local library: artists with at least `min_songs` tracks.
"""
from __future__ import annotations

import os
from collections import Counter
from typing import Dict, List, Tuple

_AUDIO_EXTS = {".mp3", ".m4a", ".mp4", ".flac", ".wav", ".ogg"}
_SKIP = {"", "unknown", "unknown artist"}


def _scan_files(root: str) -> List[str]:
    out = []
    if not root or not os.path.isdir(root):
        return out
    for dirpath, _, files in os.walk(root):
        for f in files:
            if os.path.splitext(f)[1].lower() in _AUDIO_EXTS:
                out.append(os.path.join(dirpath, f))
    return out


def get_top_artists_from_library(
    download_path: str,
    min_songs: int = 3,
    max_artists: int = 7,
) -> List[Dict]:
    """
    Returns [{ "name": str, "song_count": int }, ...] sorted by count desc.
    Only artists with >= min_songs appear.
    """
    try:
        from app.desktop.utils.metadata import get_audio_metadata
    except ImportError:
        return []

    files = _scan_files(download_path)
    counts: Counter[str] = Counter()

    for fp in files:
        try:
            meta = get_audio_metadata(fp, include_cover_data=False)
            artist = (meta.get("artist") or "").strip()
            if not artist or artist.lower() in _SKIP:
                continue
            counts[artist] += 1
        except Exception:
            continue

    ranked: List[Tuple[str, int]] = [
        (name, c) for name, c in counts.items() if c >= min_songs
    ]
    ranked.sort(key=lambda x: (-x[1], x[0].lower()))

    return [
        {"name": name, "song_count": c}
        for name, c in ranked[:max_artists]
    ]
