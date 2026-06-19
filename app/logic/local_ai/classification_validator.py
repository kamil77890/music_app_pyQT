from __future__ import annotations

import ast
import json
import re
from typing import Any

from app.logic.local_ai.metadata_normalizer import UNKNOWN_GENRE, is_garbage_genre, normalize_genre

_BROAD_GENRES = frozenset(
    {
        "rock",
        "pop",
        "electronic",
        "soundtrack",
        "classical",
        "hip hop",
        "metal",
        "jazz",
        "folk",
        "ambient",
        "dance",
        "instrumental",
        "instrumental music",
        "country",
        "blues",
        "reggae",
        "soul",
        "funk",
        "r&b",
        "indie",
        "alternative",
        "latin",
        "world",
        "punk",
        "disco",
        "house",
        "techno",
        "trance",
        "gospel",
        "unknown genre",
    }
)

_CONTEXT_LABELS = frozenset(
    {
        "anime",
        "cyberpunk",
        "game",
        "movie",
        "youtube",
        "tiktok",
        "lyrics",
        "manga",
        "tv",
        "series",
        "film",
        "videogame",
        "meme",
        "vtuber",
        "op",
        "ed",
        "opening",
        "ending",
    }
)

_STYLE_LABELS = frozenset(
    {
        "piano",
        "cover",
        "remix",
        "nightcore",
        "instrumental",
        "jumpstyle",
        "acoustic",
        "karaoke",
        "live",
        "vocal",
        "sped up",
        "slowed",
        "lo-fi",
        "lofi",
        "orchestral",
        "arrangement",
        "edit",
        "version",
        "hardstyle",
        "dubstep",
        "synthwave",
    }
)

_SOUNDTRACK_MARKERS = re.compile(
    r"\b(ost|soundtrack|opening|ending|theme|score)\b|\bop\b|\bed\b",
    re.IGNORECASE,
)

_MAX_REASON_LEN = 220
_REASON_CLAIM_MARKERS = re.compile(r"\b(manga|manhwa|light novel|tv series|video game franchise)\b", re.IGNORECASE)

_WEAK_TAGS = frozenset(
    {
        "harder",
        "different",
        "version",
        "song",
        "single",
        "edit",
        "mix",
        "audio",
        "video",
        "music",
        "track",
        "original",
        "official",
        "full",
        "hd",
        "4k",
        "hits",
        "hit",
    }
)

_TAG_NORMALIZATIONS: tuple[tuple[str, str, str | None], ...] = (
    ("rock version", "Rock", None),
    ("piano version", "Piano", "Piano"),
    ("nightcore", "Nightcore", "Nightcore"),
    ("jumpstyle", "Jumpstyle", "Jumpstyle"),
    ("lyrics", "Lyrics", None),
    ("cover", "Cover", "Cover"),
    ("remix", "Remix", "Remix"),
    ("instrumental", "Instrumental", "Instrumental"),
    ("piano", "Piano", "Piano"),
    ("rock", "Rock", None),
)


def _normalize_key(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _title_case_tag(value: str) -> str:
    text = re.sub(r"\s+", " ", value.strip())
    if not text:
        return ""
    if text.isupper() and len(text) <= 4:
        return text
    return " ".join(part.capitalize() if part.lower() not in {"and", "&", "of"} else part for part in text.split())


def _normalize_tag_candidate(tag: str, *, style: str | None) -> tuple[str | None, str | None]:
    text = _title_case_tag(tag)
    if not text:
        return None, style
    norm = _normalize_key(text)
    if norm in _WEAK_TAGS or is_garbage_genre(text):
        return None, style
    for pattern, normalized_tag, style_hint in _TAG_NORMALIZATIONS:
        if pattern in norm:
            updated_style = style
            if style_hint and not updated_style:
                updated_style = style_hint
            return normalized_tag, updated_style
    if is_context_label(text):
        return text, style
    if is_style_label(text):
        updated_style = style or text
        return text, updated_style
    return text, style


def _unique_tags(tags: list[str], *, style: str | None = None) -> tuple[list[str], str | None]:
    seen: set[str] = set()
    cleaned: list[str] = []
    current_style = style
    for tag in tags:
        text, current_style = _normalize_tag_candidate(tag, style=current_style)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned, current_style


def is_context_label(value: Any) -> bool:
    norm = _normalize_key(value)
    if not norm:
        return False
    if norm in _CONTEXT_LABELS:
        return True
    tokens = set(norm.replace("/", " ").replace("-", " ").split())
    return bool(tokens & _CONTEXT_LABELS)


def is_style_label(value: Any) -> bool:
    norm = _normalize_key(value)
    if not norm:
        return False
    if norm in _STYLE_LABELS:
        return True
    tokens = set(norm.replace("/", " ").replace("-", " ").split())
    return len(tokens) == 1 and bool(tokens & _STYLE_LABELS)


def is_broad_genre(value: Any) -> bool:
    norm = _normalize_key(normalize_genre(value))
    if norm == _normalize_key(UNKNOWN_GENRE):
        return False
    if is_context_label(norm) or is_style_label(norm):
        return False
    if norm in _BROAD_GENRES:
        return True
    # Allow multi-word broad genres the model may return, e.g. "Hip Hop", "R&B".
    return not is_garbage_genre(value) and len(norm.split()) <= 3


def _model_output_suggests_soundtrack(parsed: dict[str, Any]) -> bool:
    parts = [
        parsed.get("subgenre"),
        parsed.get("style"),
        parsed.get("collection"),
        " ".join(parsed.get("tags") or []),
        " ".join(parsed.get("mood") or []),
    ]
    text = f" {' '.join(str(part) for part in parts if part)} "
    return bool(_SOUNDTRACK_MARKERS.search(text))


def _track_suggests_soundtrack(track: dict[str, Any] | None) -> bool:
    if not track:
        return False
    haystack = " ".join(
        str(track.get(key) or "")
        for key in ("title", "album", "source_title", "sourceTitle", "description")
    )
    return bool(_SOUNDTRACK_MARKERS.search(haystack))


def _suggests_soundtrack(parsed: dict[str, Any], track: dict[str, Any] | None) -> bool:
    return _model_output_suggests_soundtrack(parsed) or _track_suggests_soundtrack(track)


def _sanitize_reason(reason: str, track: dict[str, Any] | None) -> str:
    text = re.sub(r"\s+", " ", str(reason or "").strip())
    if not text:
        return "Classified by local model."
    if len(text) > _MAX_REASON_LEN:
        text = text[: _MAX_REASON_LEN - 3].rstrip() + "..."
    if track and _REASON_CLAIM_MARKERS.search(text):
        haystack = " ".join(
            str(track.get(key) or "")
            for key in ("title", "artist", "album", "description", "source_title", "sourceTitle")
        ).lower()
        claim = _REASON_CLAIM_MARKERS.search(text)
        if claim and claim.group(0).lower() not in haystack:
            return "Classified from available metadata labels."
    return text


def _clamp_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = 0.0
    return max(0.0, min(round(confidence, 2), 1.0))


def _clean_optional_field(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value).strip())
    if not text or is_garbage_genre(text):
        return None
    return text


def _relocate_label(label: str, *, tags: list[str], style: str | None, collection: str | None) -> tuple[str | None, str | None]:
    tag_text = _title_case_tag(label)
    norm = _normalize_key(tag_text)
    if is_context_label(norm):
        if not collection:
            collection = tag_text
        tags.append(tag_text)
        return style, collection
    if is_style_label(norm):
        if not style:
            style = tag_text
        tags.append(tag_text)
        return style, collection
    tags.append(tag_text)
    return style, collection


def _coerce_field_value(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return list(value)
    if not isinstance(value, str):
        return value
    text = value.strip()
    if text.startswith("[") and text.endswith("]"):
        try:
            return json.loads(text.replace("'", '"'))
        except json.JSONDecodeError:
            try:
                parsed = ast.literal_eval(text)
                return parsed if isinstance(parsed, list) else value
            except (ValueError, SyntaxError):
                return value
    return value


def _coerce_optional_text(value: Any) -> str | None:
    coerced = _coerce_field_value(value)
    if isinstance(coerced, list):
        parts = [_title_case_tag(str(item)) for item in coerced if str(item).strip()]
        parts = [part for part in parts if part]
        return ", ".join(parts) if parts else None
    return _clean_optional_field(coerced)


def _coerce_collection(value: Any, tags: list[str]) -> str | None:
    coerced = _coerce_field_value(value)
    if isinstance(coerced, list):
        collection: str | None = None
        for item in coerced:
            text = _title_case_tag(str(item))
            if not text:
                continue
            if is_context_label(text) and collection is None:
                collection = text
            elif text.lower() not in {t.lower() for t in tags}:
                tags.append(text)
        return collection
    return _clean_optional_field(coerced)


def validate_model_classification(parsed: dict[str, Any], *, track: dict[str, Any] | None = None) -> dict[str, Any]:
    tags = [str(item).strip() for item in (parsed.get("tags") or []) if str(item).strip()]
    genre = normalize_genre(parsed.get("genre"))
    primary_genre = normalize_genre(parsed.get("primary_genre") or parsed.get("genre"))
    style = _coerce_optional_text(parsed.get("style"))
    subgenre = _clean_optional_field(parsed.get("subgenre"))
    collection = _coerce_collection(parsed.get("collection"), tags)
    mood = [str(item).strip() for item in (parsed.get("mood") or []) if str(item).strip()]
    confidence = _clamp_confidence(parsed.get("classification_confidence", 0.0))
    reason = _sanitize_reason(str(parsed.get("reason") or ""), track)
    adjusted = False

    for candidate in (genre, primary_genre):
        if is_garbage_genre(candidate):
            genre = UNKNOWN_GENRE
            primary_genre = UNKNOWN_GENRE
            adjusted = True
            break

    def fix_genre_field(value: str) -> str:
        nonlocal style, collection, tags, adjusted, confidence
        if is_garbage_genre(value) or not value or value == UNKNOWN_GENRE:
            adjusted = True
            return UNKNOWN_GENRE
        if is_context_label(value):
            style, collection = _relocate_label(value, tags=tags, style=style, collection=collection)
            adjusted = True
            confidence = min(confidence, 0.75)
            if _suggests_soundtrack(parsed, track):
                return "Soundtrack"
            return UNKNOWN_GENRE
        if is_style_label(value):
            style, collection = _relocate_label(value, tags=tags, style=style, collection=collection)
            adjusted = True
            confidence = min(confidence, 0.7)
            return UNKNOWN_GENRE
        if not is_broad_genre(value):
            style, collection = _relocate_label(value, tags=tags, style=style, collection=collection)
            adjusted = True
            confidence = min(confidence, 0.65)
            if _suggests_soundtrack(parsed, track):
                return "Soundtrack"
            return UNKNOWN_GENRE
        return normalize_genre(value)

    genre = fix_genre_field(genre)
    primary_genre = fix_genre_field(primary_genre)

    if subgenre:
        if (
            is_context_label(subgenre)
            or is_style_label(subgenre)
            or is_garbage_genre(subgenre)
            or _normalize_key(subgenre) in {"op", "ed", "opening", "ending"}
        ):
            style, collection = _relocate_label(subgenre, tags=tags, style=style, collection=collection)
            subgenre = None
            adjusted = True

    if style and (is_garbage_genre(style) or is_context_label(style)):
        style, collection = _relocate_label(style, tags=tags, style=None, collection=collection)
        adjusted = True

    if collection and is_garbage_genre(collection):
        collection = None
    if collection and is_style_label(collection):
        style, collection = _relocate_label(collection, tags=tags, style=style, collection=None)
        adjusted = True

    if genre == UNKNOWN_GENRE and primary_genre != UNKNOWN_GENRE:
        genre = primary_genre
    if primary_genre == UNKNOWN_GENRE and genre != UNKNOWN_GENRE:
        primary_genre = genre
    if genre == UNKNOWN_GENRE and primary_genre == UNKNOWN_GENRE and _suggests_soundtrack(parsed, track):
        genre = primary_genre = "Soundtrack"
        adjusted = True
    if _normalize_key(primary_genre) == "soundtrack" and genre not in {UNKNOWN_GENRE, "Soundtrack"}:
        genre = "Soundtrack"
        adjusted = True

    tag_blob = " ".join(tags).lower()
    style_blob = _normalize_key(style)
    if _normalize_key(primary_genre) == "hip hop" and ("jumpstyle" in tag_blob or style_blob == "jumpstyle"):
        confidence = min(confidence, 0.45)
        reason = "Reduced confidence: style/tags suggest jumpstyle rather than hip hop."
        adjusted = True

    if adjusted and reason == "Classified by local model.":
        reason = "Adjusted model output to use broad music genres and context tags."

    metadata_quality = str(parsed.get("metadata_quality") or "low").lower()
    if metadata_quality not in {"low", "medium", "high"}:
        metadata_quality = "low"

    tags, updated_style = _unique_tags(tags, style=style)
    if updated_style and not style:
        style = updated_style

    return {
        "genre": genre,
        "primary_genre": primary_genre,
        "style": style,
        "subgenre": subgenre,
        "collection": collection,
        "mood": mood,
        "tags": tags,
        "metadata_quality": metadata_quality,
        "classification_confidence": confidence,
        "reason": reason,
    }
