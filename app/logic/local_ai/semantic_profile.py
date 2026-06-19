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


def _should_exclude_album_from_inference(track: dict[str, Any]) -> bool:
    if track.get("_repair_managed_albums"):
        return True
    album = track.get("album") or ""
    if not album:
        return False
    from app.logic.local_ai.album_group_validator import is_ai_managed_album_folder

    return is_ai_managed_album_folder(album)


def _track_haystack(track: dict[str, Any]) -> str:
    keys = ("title", "artist", "source_title", "sourceTitle", "description")
    if not _should_exclude_album_from_inference(track):
        keys = ("title", "artist", "album", "source_title", "sourceTitle", "description")
    return " ".join(str(track.get(key) or "") for key in keys)


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


def _filter_style_markers(
    style_markers: list[str],
    *,
    context_markers: list[str],
    track: dict[str, Any],
) -> list[str]:
    styles = {_normalize_key(item) for item in style_markers}
    contexts = {_normalize_key(item) for item in context_markers}
    haystack = _normalize_key(_track_haystack(track))
    filtered = list(style_markers)
    if "nightcore" in styles and "nightcore" not in haystack:
        if "piano" in styles and ({"anime", "soundtrack"} & contexts or "anime" in haystack or "op" in haystack):
            filtered = [item for item in filtered if _normalize_key(item) != "nightcore"]
    return _dedupe_preserve(filtered)


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


def _normalize_context_markers(markers: list[str]) -> list[str]:
    normalized: list[str] = []
    for marker in markers:
        key = _normalize_key(marker)
        if not key:
            continue
        if "anime" in key:
            normalized.append("anime")
        if "soundtrack" in key or "ost" in key or "amv" in key:
            normalized.append("soundtrack")
        if _VIDEO_MARKER.search(key) or key in {"music video", "mv"}:
            normalized.append("music video")
        elif key not in {"anime", "soundtrack", "music video"}:
            normalized.append(marker.strip())
    return _dedupe_preserve(normalized)


def infer_context_markers(track: dict[str, Any], *, tags: list[str] | None = None) -> list[str]:
    haystack = _normalize_key(_track_haystack(track))
    tag_blob = " ".join(_normalize_key(tag) for tag in (tags or []))
    markers: list[str] = []
    if _ANIME_MARKER.search(haystack) or "anime" in tag_blob or "amv" in haystack:
        markers.append("anime")
    if _OST_MARKER.search(haystack) or "ost" in tag_blob or "soundtrack" in tag_blob or "amv" in haystack:
        markers.append("soundtrack")
    if _VIDEO_MARKER.search(haystack) or "amv" in haystack:
        markers.append("music video")
    return _normalize_context_markers(markers)


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
    broad_genre = normalize_genre(genre)
    style_markers = infer_style_markers(track, style=style, tags=tags)
    context_markers = infer_context_markers(track, tags=tags)
    performance_type = infer_performance_type(track, style=style, tags=tags)
    theme = infer_likely_group_theme(track, genre=genre, style=style, tags=tags)

    fallback = {
        "main_genre": broad_genre,
        "broad_genre": broad_genre,
        "style_markers": _filter_style_markers(style_markers, context_markers=context_markers, track=track),
        "context_markers": context_markers,
        "performance_type": performance_type,
        "likely_group_theme": theme,
        "theme": theme,
        "energy": "",
    }
    if not isinstance(model_profile, dict):
        return fallback

    main_genre = normalize_genre(model_profile.get("main_genre") or model_profile.get("broad_genre") or fallback["main_genre"])
    model_styles = [str(item).strip() for item in (model_profile.get("style_markers") or []) if str(item).strip()]
    model_contexts = [str(item).strip() for item in (model_profile.get("context_markers") or []) if str(item).strip()]
    style_markers = _dedupe_preserve(model_styles + fallback["style_markers"])
    context_markers = _normalize_context_markers(_dedupe_preserve(model_contexts + fallback["context_markers"]))
    performance_type = str(model_profile.get("performance_type") or fallback["performance_type"]).strip().lower() or fallback["performance_type"]
    theme = str(model_profile.get("theme") or model_profile.get("likely_group_theme") or "").strip().lower() or fallback["theme"]
    style_markers = _filter_style_markers(style_markers, context_markers=context_markers, track=track)
    return {
        "main_genre": main_genre,
        "broad_genre": main_genre,
        "style_markers": style_markers,
        "context_markers": context_markers,
        "performance_type": performance_type,
        "likely_group_theme": theme,
        "theme": theme,
        "energy": str(model_profile.get("energy") or "").strip(),
    }


def semantic_fingerprint(profile: dict[str, Any]) -> str:
    from app.logic.local_ai.album_group_canonical import canonical_cluster_key

    return canonical_cluster_key(profile)


def grouping_fingerprint(profile: dict[str, Any]) -> str:
    from app.logic.local_ai.album_group_canonical import canonical_cluster_key

    return canonical_cluster_key(profile)
