from __future__ import annotations

import re


UNKNOWN_ARTIST = "Unknown Artist"
UNKNOWN_ALBUM = "Unknown Album"
UNKNOWN_GENRE = "Unknown Genre"

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_HEX_HASH_RE = re.compile(r"^[a-fA-F0-9]{16,}$")
_RANDOM_ID_RE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9_-]{10,}$")
_EMPTY_VALUES = {"", "n/a", "none", "null", "unknown", "unknown genre", "-"}
_GENRE_ALIASES = {
    "hiphop": "Hip Hop",
    "hip hop": "Hip Hop",
    "hip-hop": "Hip Hop",
    "r&b": "R&B",
    "rnb": "R&B",
    "edm": "Electronic",
    "lofi": "Electronic",
    "lo-fi": "Electronic",
    "night core": "Nightcore",
    "nightcore": "Nightcore",
}


def _clean_text(value) -> str:
    text = str(value or "").replace("\x00", "").strip()
    return re.sub(r"\s+", " ", text)


def normalize_artist(value) -> str:
    text = _clean_text(value)
    if text.lower() in _EMPTY_VALUES:
        return UNKNOWN_ARTIST
    text = re.sub(r"\s+-\s+Topic$", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"\s+VEVO$", "", text, flags=re.IGNORECASE).strip()
    return text or UNKNOWN_ARTIST


def normalize_album(value) -> str:
    text = _clean_text(value)
    if text.lower() in _EMPTY_VALUES:
        return UNKNOWN_ALBUM
    if is_garbage_genre(text):
        return UNKNOWN_ALBUM
    return text


def is_garbage_genre(value) -> bool:
    text = _clean_text(value)
    if text.lower() in _EMPTY_VALUES:
        return True
    if _VIDEO_ID_RE.match(text):
        return True
    if _HEX_HASH_RE.match(text):
        return True
    if _RANDOM_ID_RE.match(text) and not any(ch.isspace() for ch in text):
        return True
    return False


def normalize_genre(value) -> str:
    text = _clean_text(value)
    if is_garbage_genre(text):
        return UNKNOWN_GENRE
    key = text.lower().replace("_", "-")
    if key in _GENRE_ALIASES:
        return _GENRE_ALIASES[key]
    if text.isupper() and len(text) > 3:
        return text
    return " ".join(part.capitalize() if part.lower() not in {"and", "&"} else part for part in text.split())


def calculate_metadata_quality(metadata: dict) -> str:
    title = _clean_text(metadata.get("title"))
    artist = normalize_artist(metadata.get("artist"))
    album = normalize_album(metadata.get("album"))
    genre = normalize_genre(metadata.get("genre"))
    score = 0
    if title and title.lower() not in _EMPTY_VALUES:
        score += 1
    if artist != UNKNOWN_ARTIST:
        score += 1
    if album != UNKNOWN_ALBUM:
        score += 1
    if genre != UNKNOWN_GENRE:
        score += 1
    if score >= 4:
        return "high"
    if score >= 2:
        return "medium"
    return "low"
