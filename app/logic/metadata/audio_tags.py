"""Lightweight genre/year extraction (mutagen) — server-side substitute for desktop metadata helpers."""

from __future__ import annotations

import os
from typing import Any

from app.logic.local_ai.metadata_normalizer import UNKNOWN_GENRE, normalize_genre


def read_genre_year(file_path: str) -> dict[str, Any]:
    """Return subset of tags used by tagging / enrichment (genre, year as four-digit string)."""
    out: dict[str, Any] = {}
    if not file_path or not os.path.isfile(file_path):
        return out
    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext == ".mp3":
            _read_mp3_tags(file_path, out)
        elif ext in (".m4a", ".mp4"):
            _read_mp4_tags(file_path, out)
    except Exception:
        return out
    return out


def _year_from_text(text: str) -> str | None:
    t = (text or "").strip()
    if len(t) >= 4 and t[:4].isdigit():
        return t[:4]
    return None


def _read_mp3_tags(file_path: str, out: dict[str, Any]) -> None:
    from mutagen.mp3 import MP3
    from mutagen.easyid3 import EasyID3
    from mutagen.id3 import ID3, ID3NoHeaderError

    try:
        audio = MP3(file_path, ID3=EasyID3)
        if audio.tags:
            g = audio.tags.get("genre")
            if g:
                genre = normalize_genre(str(g[0]))
                if genre != UNKNOWN_GENRE:
                    out["genre"] = genre
            d = audio.tags.get("date")
            if d:
                y = _year_from_text(str(d[0]))
                if y:
                    out["year"] = y
    except Exception:
        pass

    try:
        id3 = ID3(file_path)
        for key in ("TDRC", "TYER", "TDOR"):
            if key not in id3:
                continue
            frame = id3[key]
            if hasattr(frame, "text") and frame.text:
                raw = frame.text[0]
                y = _year_from_text(str(raw))
                if y:
                    out["year"] = y
                    break
            else:
                y = _year_from_text(str(frame))
                if y:
                    out["year"] = y
                    break
    except ID3NoHeaderError:
        pass
    except Exception:
        pass


def _read_mp4_tags(file_path: str, out: dict[str, Any]) -> None:
    from mutagen.mp4 import MP4

    audio = MP4(file_path)
    if "\xa9gen" in audio and audio["\xa9gen"]:
        genre = normalize_genre(str(audio["\xa9gen"][0]))
        if genre != UNKNOWN_GENRE:
            out["genre"] = genre
    if "\xa9day" in audio and audio["\xa9day"]:
        y = _year_from_text(str(audio["\xa9day"][0]))
        if y:
            out["year"] = y
