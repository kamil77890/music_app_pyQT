from __future__ import annotations

import re
from dataclasses import dataclass
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

_VALID_FALLBACK_ALBUMS = ("Singles", "Live Recordings")

_COLLECTION_NAMES = (
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
    "Live Recordings",
)

FAKE_CATEGORY_ALBUM_FOLDERS: frozenset[str] = frozenset(_COLLECTION_NAMES)

_COLLECTION_LOOKUP = {name.lower(): name for name in _COLLECTION_NAMES}

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


@dataclass(frozen=True)
class AlbumMetadataResult:
    album: str
    collection: str | None
    album_source: str
    album_confidence: float


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


def _canonical_collection_name(value: str) -> str | None:
    norm = _normalize_key(value)
    if norm in _COLLECTION_LOOKUP:
        return _COLLECTION_LOOKUP[norm]
    return None


def is_fake_category_album(value: Any) -> bool:
    cleaned = sanitize_album_name(value)
    if not cleaned:
        return False
    return _canonical_collection_name(cleaned) is not None


def is_repairable_source_album_folder(folder_name: str) -> bool:
    name = sanitize_album_name(folder_name)
    if not name:
        return False
    if _normalize_key(name) == _normalize_key(UNKNOWN_ALBUM):
        return True
    return is_fake_category_album(name)


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
    if is_fake_category_album(album):
        return False
    if is_garbage_genre(album):
        return False
    if _album_matches_title_or_artist(album, track):
        return False
    return True


def _is_live_track(
    track: dict[str, Any] | None,
    *,
    style: str | None = None,
    tags: list[str] | None = None,
) -> bool:
    haystack = _normalize_key(_track_proof_haystack(track))
    style_norm = _normalize_key(style) if style else ""
    tag_blob = " ".join(_normalize_key(tag) for tag in (tags or []))
    return bool(_LIVE_MARKER.search(haystack) or style_norm == "live" or "live" in tag_blob)


def deterministic_album_fallback(
    track: dict[str, Any] | None,
    *,
    style: str | None = None,
    tags: list[str] | None = None,
) -> str:
    if _is_live_track(track, style=style, tags=tags):
        return "Live Recordings"
    return "Singles"


def deterministic_collection_fallback(
    track: dict[str, Any] | None,
    *,
    genre: str = "Unknown Genre",
    style: str | None = None,
    tags: list[str] | None = None,
) -> str | None:
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
    if _is_live_track(track, style=style, tags=tags):
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
    return None


def _normalize_collection_value(value: Any) -> str | None:
    text = sanitize_album_name(value)
    if not text:
        return None
    return _canonical_collection_name(text)


def resolve_track_album_metadata(
    *,
    track: dict[str, Any],
    model_album: Any = None,
    model_collection: Any = None,
    genre: str = "Unknown Genre",
    style: str | None = None,
    tags: list[str] | None = None,
    repair_managed_albums: bool = False,
) -> AlbumMetadataResult:
    existing = sanitize_album_name(track.get("album") or "")
    if not existing:
        existing = normalize_album(track.get("album"))

    existing_is_real = is_real_album(existing, track=track)
    existing_is_fake = is_fake_category_album(existing)
    needs_replacement = (
        repair_managed_albums
        or is_missing_album(existing)
        or is_rejected_album_label(existing)
        or existing_is_fake
        or not existing_is_real
    )

    if existing_is_real:
        collection = _normalize_collection_value(model_collection) or deterministic_collection_fallback(
            track, genre=genre, style=style, tags=tags
        )
        return AlbumMetadataResult(existing, collection, "existing", 1.0)

    raw_album = str(model_album or "").strip()
    raw_collection = _normalize_collection_value(model_collection)
    collection_from_album = _normalize_collection_value(raw_album) if raw_album else None

    if collection_from_album:
        raw_collection = raw_collection or collection_from_album
        album = deterministic_album_fallback(track, style=style, tags=tags)
        source = "local_ai" if raw_album else "fallback"
        confidence = 0.75 if source == "local_ai" else 0.55
        return AlbumMetadataResult(album, raw_collection, source, confidence)

    if raw_album and is_real_album(raw_album, track=track):
        collection = raw_collection or deterministic_collection_fallback(track, genre=genre, style=style, tags=tags)
        return AlbumMetadataResult(sanitize_album_name(raw_album), collection, "local_ai", 0.85)

    album = deterministic_album_fallback(track, style=style, tags=tags)
    collection = raw_collection or deterministic_collection_fallback(track, genre=genre, style=style, tags=tags)
    confidence = 0.55 if collection else 0.35
    source = "local_ai" if (raw_album or raw_collection) and needs_replacement else "fallback"
    return AlbumMetadataResult(album, collection, source, confidence)


def resolve_track_album(
    *,
    track: dict[str, Any],
    model_album: Any = None,
    model_collection: Any = None,
    genre: str = "Unknown Genre",
    style: str | None = None,
    tags: list[str] | None = None,
    repair_managed_albums: bool = False,
) -> tuple[str, str, float]:
    result = resolve_track_album_metadata(
        track=track,
        model_album=model_album,
        model_collection=model_collection,
        genre=genre,
        style=style,
        tags=tags,
        repair_managed_albums=repair_managed_albums,
    )
    return result.album, result.album_source, result.album_confidence


def validate_album_suggestion(
    raw_album: Any,
    *,
    track: dict[str, Any] | None,
    genre: str,
    style: str | None = None,
    tags: list[str] | None = None,
    model_collection: Any = None,
) -> tuple[str, str | None, float]:
    result = resolve_track_album_metadata(
        track=track or {},
        model_album=raw_album,
        model_collection=model_collection,
        genre=genre,
        style=style,
        tags=tags,
    )
    return result.album, result.collection, result.album_confidence
