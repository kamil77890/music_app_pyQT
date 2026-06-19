from __future__ import annotations

import re
from typing import Any

from app.logic.local_ai.metadata_normalizer import (
    UNKNOWN_ALBUM,
    is_garbage_genre,
    normalize_album,
    normalize_artist,
)

_MAX_GROUP_NAME_LEN = 80
_BANNED_GROUP_WORDS = frozenset(
    {
        "unknown",
        "singles",
        "misc",
        "general",
        "music",
        "collection",
        "other",
        "youtube",
        "n/a",
        "none",
        "null",
    }
)
_REJECTED_ALBUM_LABELS = frozenset(
    {
        "unknown album",
        "unknown",
        "misc",
        "other",
        "general",
        "music",
        "youtube",
        "n/a",
        "none",
        "null",
        "audio",
        "video",
        "song",
        "songs",
    }
)

LEGACY_MANAGED_ALBUM_FOLDERS: frozenset[str] = frozenset(
    {
        "Singles",
        "Unknown Album",
        "Live Recordings",
        "Music Videos",
        "Nightcore Collection",
        "Rock Versions",
        "Piano Versions",
        "Piano Covers",
        "Soundtrack Collection",
        "OST Collection",
        "Anime Soundtracks",
        "Classical Piano",
        "Electronic Collection",
        "Pop Collection",
        "Rock Collection",
        "Dance Collection",
    }
)

_PATH_UNSAFE_RE = re.compile(r'[/\\:*?"<>|]')


def _normalize_key(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def sanitize_group_name(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").replace("\x00", "").strip())
    text = _PATH_UNSAFE_RE.sub("", text)
    text = text.replace("..", "")
    text = text.strip(" .")
    if not text:
        return ""
    if len(text) > _MAX_GROUP_NAME_LEN:
        text = text[:_MAX_GROUP_NAME_LEN].rstrip(" .")
    return text


def is_missing_album(value: Any) -> bool:
    return normalize_album(value) == UNKNOWN_ALBUM


def is_legacy_managed_album_folder(name: Any) -> bool:
    cleaned = sanitize_group_name(name)
    if not cleaned:
        return False
    lookup = {_normalize_key(item): item for item in LEGACY_MANAGED_ALBUM_FOLDERS}
    return _normalize_key(cleaned) in lookup


def is_repairable_source_album_folder(folder_name: str) -> bool:
    name = sanitize_group_name(folder_name)
    if not name:
        return False
    if _normalize_key(name) == _normalize_key(UNKNOWN_ALBUM):
        return True
    return is_legacy_managed_album_folder(name)


def _album_matches_title_or_artist(album: str, track: dict[str, Any] | None) -> bool:
    if not track or not album:
        return False
    album_norm = _normalize_key(album)
    title_norm = _normalize_key(track.get("title"))
    artist_norm = _normalize_key(normalize_artist(track.get("artist")))
    if album_norm and (album_norm == title_norm or album_norm == artist_norm):
        return True
    if title_norm and len(title_norm) >= 8 and album_norm in title_norm:
        return True
    return False


def is_official_or_existing_album(value: Any, *, track: dict[str, Any] | None = None) -> bool:
    album = sanitize_group_name(value)
    if not album or is_missing_album(album) or _normalize_key(album) in _REJECTED_ALBUM_LABELS:
        return False
    if is_legacy_managed_album_folder(album):
        return False
    if is_garbage_genre(album):
        return False
    if _album_matches_title_or_artist(album, track):
        return False
    return True


def _contains_banned_word(name: str) -> bool:
    words = set(_normalize_key(name).split())
    return bool(words & _BANNED_GROUP_WORDS)


def is_weak_group_name(name: str, *, track: dict[str, Any] | None = None, artist: str | None = None) -> bool:
    cleaned = sanitize_group_name(name)
    if not cleaned:
        return True
    if _contains_banned_word(cleaned):
        return True
    if track and _album_matches_title_or_artist(cleaned, track):
        return True
    if artist and _normalize_key(cleaned) == _normalize_key(artist):
        return True
    word_count = len(cleaned.split())
    if word_count < 1 or word_count > 6:
        return True
    return False


def _title_case_phrase(value: str) -> str:
    return " ".join(part.capitalize() for part in value.split())


def build_deterministic_group_name(profile: dict[str, Any]) -> str:
    context = [str(item) for item in (profile.get("context_markers") or []) if str(item).strip()]
    styles = [str(item) for item in (profile.get("style_markers") or []) if str(item).strip()]
    genre = _normalize_key(profile.get("main_genre") or "")
    parts: list[str] = []

    if context and styles:
        parts.append(_title_case_phrase(f"{context[0]} {styles[0]}"))
        if len(styles) > 1:
            parts.append(_title_case_phrase(styles[1]))
    elif styles:
        if genre and genre not in {_normalize_key(style) for style in styles}:
            parts.append(_title_case_phrase(f"{styles[0]} {genre}"))
        else:
            parts.append(_title_case_phrase(styles[0]))
    elif context:
        parts.append(_title_case_phrase(f"{context[0]} {genre or 'tracks'}"))
    elif genre:
        parts.append(_title_case_phrase(f"{genre} tracks"))
    else:
        parts.append("Library Tracks")

    candidate = " ".join(parts[:2]).strip()
    return sanitize_group_name(candidate) or "Library Tracks"


def _strip_artist_suffix(name: str, artist: str | None) -> str:
    if not artist:
        return name
    artist_norm = _normalize_key(artist)
    name_norm = _normalize_key(name)
    if name_norm == artist_norm:
        return ""
    for separator in (" - ", " – "):
        if separator in name and _normalize_key(name.split(separator)[-1]) == artist_norm:
            return name.rsplit(separator, 1)[0].strip()
    if name_norm.endswith(f" {artist_norm}"):
        return name[: -len(artist)].strip(" -")
    return name


def validate_group_name(
    raw_name: Any,
    *,
    profile: dict[str, Any],
    track: dict[str, Any] | None = None,
    artist: str | None = None,
) -> str:
    cleaned = sanitize_group_name(_strip_artist_suffix(sanitize_group_name(raw_name), artist))
    if cleaned and not is_weak_group_name(cleaned, track=track, artist=artist):
        return cleaned
    return build_deterministic_group_name(profile)
