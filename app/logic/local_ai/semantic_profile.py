from __future__ import annotations

import re
from typing import Any

from app.logic.local_ai.metadata_normalizer import UNKNOWN_GENRE, normalize_genre

_LIVE_MARKER = re.compile(r"\blive\b", re.IGNORECASE)
_NIGHTCORE_MARKER = re.compile(r"\bnightcore\b", re.IGNORECASE)
_PIANO_MARKER = re.compile(r"\b(piano|piano version|piano cover|piano arrangement|arr\.?)\b", re.IGNORECASE)
_OST_MARKER = re.compile(r"\b(ost|soundtrack|opening|ending)\b|\bop\b|\bed\b", re.IGNORECASE)
_ANIME_MARKER = re.compile(r"\b(anime|episode|series)\b", re.IGNORECASE)
_ROCK_MARKER = re.compile(r"\b(rock|rock version|alternative)\b", re.IGNORECASE)
_POP_MARKER = re.compile(r"\bpop\b", re.IGNORECASE)
_CLASSICAL_MARKER = re.compile(r"\b(beethoven|sonata|symphony|concerto|classical|moonlight sonata)\b", re.IGNORECASE)
_COVER_MARKER = re.compile(r"\b(cover|remix|arrangement)\b", re.IGNORECASE)
_VIDEO_MARKER = re.compile(r"\b(official music video|official video|music video|mv|amv)\b", re.IGNORECASE)


def _normalize_key(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _track_haystack(track: dict[str, Any]) -> str:
    return " ".join(
        str(track.get(key) or "")
        for key in ("title", "artist", "album", "source_title", "sourceTitle", "description")
    )


def _dedupe_preserve(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = _normalize_key(item)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def infer_performance_type(track: dict[str, Any], *, style: str | None = None, tags: list[str] | None = None) -> str:
    haystack = _normalize_key(_track_haystack(track))
    style_norm = _normalize_key(style)
    tag_blob = " ".join(_normalize_key(tag) for tag in (tags or []))
    if _LIVE_MARKER.search(haystack) or style_norm == "live" or "live" in tag_blob:
        return "live"
    if _COVER_MARKER.search(haystack) or style_norm in {"cover", "piano"}:
        return "cover"
    if _VIDEO_MARKER.search(haystack):
        return "video"
    return "studio"


def infer_context_markers(track: dict[str, Any], *, tags: list[str] | None = None) -> list[str]:
    haystack = _normalize_key(_track_haystack(track))
    tag_blob = " ".join(_normalize_key(tag) for tag in (tags or []))
    markers: list[str] = []
    if _ANIME_MARKER.search(haystack) or "anime" in tag_blob:
        markers.append("anime")
    if _OST_MARKER.search(haystack) or "ost" in tag_blob or "soundtrack" in tag_blob:
        markers.append("soundtrack")
    if _VIDEO_MARKER.search(haystack):
        markers.append("music video")
    return _dedupe_preserve(markers)


def infer_style_markers(track: dict[str, Any], *, style: str | None = None, tags: list[str] | None = None) -> list[str]:
    haystack = _normalize_key(_track_haystack(track))
    style_norm = _normalize_key(style)
    tag_blob = " ".join(_normalize_key(tag) for tag in (tags or []))
    markers: list[str] = []
    if style_norm:
        markers.append(style_norm)
    if _NIGHTCORE_MARKER.search(haystack) or "nightcore" in tag_blob:
        markers.append("nightcore")
    if _PIANO_MARKER.search(haystack) or "piano" in tag_blob:
        markers.append("piano")
    if _ROCK_MARKER.search(haystack) or "rock" in tag_blob:
        markers.append("rock")
    if _POP_MARKER.search(haystack) or "pop" in tag_blob:
        markers.append("pop")
    if _CLASSICAL_MARKER.search(haystack) or "classical" in tag_blob:
        markers.append("classical")
    return _dedupe_preserve(markers)


def infer_likely_group_theme(
    track: dict[str, Any],
    *,
    genre: str,
    style: str | None = None,
    tags: list[str] | None = None,
) -> str:
    context = infer_context_markers(track, tags=tags)
    styles = infer_style_markers(track, style=style, tags=tags)
    genre_norm = _normalize_key(normalize_genre(genre))
    if genre_norm == _normalize_key(UNKNOWN_GENRE):
        genre_norm = ""

    parts: list[str] = []
    if context:
        parts.extend(context[:2])
    if styles:
        parts.extend(styles[:2])
    if genre_norm:
        parts.append(genre_norm)
    if not parts:
        parts.append("library tracks")
    return " ".join(parts[:4])


def build_semantic_profile(
    track: dict[str, Any],
    *,
    genre: str,
    style: str | None = None,
    tags: list[str] | None = None,
    model_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fallback = {
        "main_genre": normalize_genre(genre),
        "style_markers": infer_style_markers(track, style=style, tags=tags),
        "context_markers": infer_context_markers(track, tags=tags),
        "performance_type": infer_performance_type(track, style=style, tags=tags),
        "likely_group_theme": infer_likely_group_theme(track, genre=genre, style=style, tags=tags),
    }
    if not isinstance(model_profile, dict):
        return fallback

    main_genre = normalize_genre(model_profile.get("main_genre") or fallback["main_genre"])
    style_markers = _dedupe_preserve(
        [str(item).strip() for item in (model_profile.get("style_markers") or []) if str(item).strip()]
        or fallback["style_markers"]
    )
    context_markers = _dedupe_preserve(
        [str(item).strip() for item in (model_profile.get("context_markers") or []) if str(item).strip()]
        or fallback["context_markers"]
    )
    performance_type = str(model_profile.get("performance_type") or fallback["performance_type"]).strip().lower() or fallback["performance_type"]
    likely_group_theme = str(model_profile.get("likely_group_theme") or "").strip().lower() or fallback["likely_group_theme"]
    return {
        "main_genre": main_genre,
        "style_markers": style_markers,
        "context_markers": context_markers,
        "performance_type": performance_type,
        "likely_group_theme": likely_group_theme,
    }


def semantic_fingerprint(profile: dict[str, Any]) -> str:
    return _normalize_key(profile.get("likely_group_theme") or "")


def grouping_fingerprint(profile: dict[str, Any]) -> str:
    theme = _normalize_key(profile.get("likely_group_theme") or "")
    theme = re.sub(r"\blive\b", "", theme).strip()
    if not theme:
        styles = " ".join(_normalize_key(item) for item in (profile.get("style_markers") or []))
        theme = re.sub(r"\blive\b", "", styles).strip()
    if not theme:
        theme = _normalize_key(profile.get("main_genre") or "library tracks")
    return re.sub(r"\s+", " ", theme).strip()
