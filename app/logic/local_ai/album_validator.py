from __future__ import annotations

import re
from typing import Any

from app.logic.local_ai.metadata_normalizer import (
    UNKNOWN_ALBUM,
    UNKNOWN_ARTIST,
    is_garbage_genre,
    normalize_album,
    normalize_artist,
    normalize_genre,
)

_MAX_ALBUM_LEN = 80
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

_ALLOWED_COLLECTION_ALBUMS = (
    "Singles",
    "Music Videos",
    "Live Recordings",
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
)

_ALLOWED_COLLECTION_LOOKUP = {name.lower(): name for name in _ALLOWED_COLLECTION_ALBUMS}

_PATH_UNSAFE_RE = re.compile(r'[/\\:*?"<>|]')
_NIGHTCORE_MARKER = re.compile(r"\bnightcore\b", re.IGNORECASE)
_ROCK_VERSION_MARKER = re.compile(r"\brock version\b", re.IGNORECASE)
_PIANO_MARKER = re.compile(r"\b(piano|piano version|piano cover|piano arrangement|arr\.?)\b", re.IGNORECASE)
_PIANO_COVER_MARKER = re.compile(r"\b(piano cover|cover)\b", re.IGNORECASE)
_OST_MARKER = re.compile(r"\b(ost|soundtrack)\b", re.IGNORECASE)
_ANIME_SOUNDTRACK_MARKER = re.compile(
    r"\b(anime|opening|ending|episode|series)\b|\bop\b|\bed\b",
    re.IGNORECASE,
)
_LIVE_MARKER = re.compile(r"\blive\b", re.IGNORECASE)
_OFFICIAL_VIDEO_MARKER = re.compile(r"\b(official music video|official video)\b", re.IGNORECASE)
_CLASSICAL_MARKER = re.compile(r"\b(beethoven|sonata|symphony|concerto|classical|moonlight sonata)\b", re.IGNORECASE)


def _normalize_key(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _track_proof_haystack(track: dict[str, Any] | None) -> str:
    if not track:
        return ""
    return " ".join(
        str(track.get(key) or "")
        for key in ("title", "artist", "album", "source_title", "sourceTitle", "description")
    )


def is_missing_album(value: Any) -> bool:
    return normalize_album(value) == UNKNOWN_ALBUM


def is_rejected_album_label(value: Any) -> bool:
    norm = _normalize_key(value)
    return not norm or norm in _REJECTED_ALBUM_LABELS


def sanitize_album_name(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").replace("\x00", "").strip())
    text = _PATH_UNSAFE_RE.sub("", text)
    text = text.replace("..", "")
    text = text.strip(" .")
    if not text:
        return ""
    if len(text) > _MAX_ALBUM_LEN:
        text = text[:_MAX_ALBUM_LEN].rstrip(" .")
    return text


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


def is_real_album(value: Any, *, track: dict[str, Any] | None = None) -> bool:
    album = sanitize_album_name(value)
    if not album or is_missing_album(album) or is_rejected_album_label(album):
        return False
    if is_garbage_genre(album):
        return False
    if _album_matches_title_or_artist(album, track):
        return False
    return True


def _canonical_allowed_collection(value: str) -> str | None:
    norm = _normalize_key(value)
    if norm in _ALLOWED_COLLECTION_LOOKUP:
        return _ALLOWED_COLLECTION_LOOKUP[norm]
    return None


def deterministic_album_fallback(
    track: dict[str, Any] | None,
    *,
    genre: str = "Unknown Genre",
    style: str | None = None,
    tags: list[str] | None = None,
) -> str:
    haystack = _normalize_key(_track_proof_haystack(track))
    tag_blob = " ".join(_normalize_key(tag) for tag in (tags or []))
    genre_norm = _normalize_key(normalize_genre(genre))
    style_norm = _normalize_key(style) if style else ""

    if _NIGHTCORE_MARKER.search(haystack) or style_norm == "nightcore" or "nightcore" in tag_blob:
        return "Nightcore Collection"
    if _ROCK_VERSION_MARKER.search(haystack):
        return "Rock Versions"
    if _OST_MARKER.search(haystack) or "ost" in tag_blob or "soundtrack" in tag_blob:
        if _ANIME_SOUNDTRACK_MARKER.search(haystack) or "anime" in tag_blob:
            return "Anime Soundtracks"
        return "OST Collection"
    if _ANIME_SOUNDTRACK_MARKER.search(haystack) or "anime" in tag_blob:
        return "Anime Soundtracks"
    if genre_norm == "classical" and (_CLASSICAL_MARKER.search(haystack) or style_norm == "piano"):
        return "Classical Piano"
    if _PIANO_COVER_MARKER.search(haystack):
        return "Piano Covers"
    if _PIANO_MARKER.search(haystack) or style_norm == "piano" or "piano" in tag_blob:
        return "Piano Versions"
    if _LIVE_MARKER.search(haystack) or style_norm == "live":
        return "Live Recordings"
    if _OFFICIAL_VIDEO_MARKER.search(haystack):
        return "Music Videos"
    if genre_norm == "pop":
        return "Pop Collection"
    if genre_norm == "rock":
        return "Rock Collection"
    if genre_norm == "electronic":
        return "Electronic Collection"
    if genre_norm == "dance":
        return "Dance Collection"
    if genre_norm == "soundtrack":
        return "Soundtrack Collection"
    return "Singles"


def validate_album_suggestion(
    raw_album: Any,
    *,
    track: dict[str, Any] | None,
    genre: str,
    style: str | None = None,
    tags: list[str] | None = None,
) -> tuple[str, float]:
    cleaned = sanitize_album_name(raw_album)
    allowed = _canonical_allowed_collection(cleaned) if cleaned else None
    if allowed:
        return allowed, 0.75
    if cleaned and is_real_album(cleaned, track=track):
        return cleaned, 0.85
    fallback = deterministic_album_fallback(track, genre=genre, style=style, tags=tags)
    confidence = 0.55 if fallback != "Singles" else 0.35
    return fallback, confidence


def resolve_track_album(
    *,
    track: dict[str, Any],
    model_album: Any = None,
    genre: str = "Unknown Genre",
    style: str | None = None,
    tags: list[str] | None = None,
    repair_managed_albums: bool = False,
) -> tuple[str, str, float]:
    existing = sanitize_album_name(track.get("album") or "")
    if not existing:
        existing = normalize_album(track.get("album"))

    if is_real_album(existing, track=track) and not repair_managed_albums:
        return existing, "existing", 1.0

    if is_missing_album(existing) or repair_managed_albums or is_rejected_album_label(existing):
        if model_album and str(model_album).strip():
            album, confidence = validate_album_suggestion(
                model_album,
                track=track,
                genre=genre,
                style=style,
                tags=tags,
            )
            return album, "local_ai", confidence
        album = deterministic_album_fallback(track, genre=genre, style=style, tags=tags)
        confidence = 0.55 if album != "Singles" else 0.35
        return album, "fallback", confidence

    if model_album and str(model_album).strip():
        album, confidence = validate_album_suggestion(
            model_album,
            track=track,
            genre=genre,
            style=style,
            tags=tags,
        )
        return album, "local_ai", confidence

    return existing, "existing", 0.5
