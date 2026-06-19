from __future__ import annotations

import re
from typing import Any

from app.logic.local_ai.album_group_canonical import (
    build_group_name_from_cluster,
    canonicalize_group_name,
    is_weak_group_name,
)
from app.logic.local_ai.metadata_normalizer import (
    UNKNOWN_ALBUM,
    is_garbage_genre,
    normalize_album,
    normalize_artist,
)

_MAX_GROUP_NAME_LEN = 80
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


_AI_MANAGED_FOLDER_PREFIXES = (
    "music video",
    "live ",
    "soundtrack ",
    "nightcore ",
)


def is_ai_managed_album_folder(name: Any) -> bool:
    cleaned = sanitize_group_name(name)
    if not cleaned:
        return False
    if is_legacy_managed_album_folder(cleaned):
        return True
    normalized = _normalize_key(cleaned)
    if any(normalized.startswith(prefix) for prefix in _AI_MANAGED_FOLDER_PREFIXES):
        return True
    if normalized.endswith(" amv") or normalized.endswith(" nightcore") or " amv " in normalized:
        return True
    if is_weak_group_name(cleaned):
        return True
    return False


def is_repairable_source_album_folder(folder_name: str) -> bool:
    name = sanitize_group_name(folder_name)
    if not name:
        return False
    if _normalize_key(name) == _normalize_key(UNKNOWN_ALBUM):
        return True
    return is_ai_managed_album_folder(name)


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
    if is_ai_managed_album_folder(album):
        return False
    if is_garbage_genre(album):
        return False
    if _album_matches_title_or_artist(album, track):
        return False
    return True


def build_deterministic_group_name(profile: dict[str, Any]) -> str:
    return build_group_name_from_cluster([profile])


def validate_group_name(
    raw_name: Any,
    *,
    profile: dict[str, Any] | None = None,
    profiles: list[dict[str, Any]] | None = None,
    track: dict[str, Any] | None = None,
    artist: str | None = None,
) -> str:
    cluster_profiles = profiles or ([profile] if profile else [])
    if artist and cluster_profiles:
        artist_norm = _normalize_key(artist)
        cleaned = sanitize_group_name(raw_name)
        if cleaned and _normalize_key(cleaned) == artist_norm:
            return build_group_name_from_cluster(cluster_profiles)
    if cluster_profiles:
        return canonicalize_group_name(str(raw_name or ""), cluster_profiles)
    return sanitize_group_name(raw_name) or "Library"
