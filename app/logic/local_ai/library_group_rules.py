from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from app.logic.local_ai.album_group_canonical import build_group_name_from_cluster
from app.logic.local_ai.metadata_normalizer import UNKNOWN_GENRE, normalize_genre

GROUPING_CONFIG_VERSION = "library-layout-v1"

_NIGHTCORE_RE = re.compile(r"\bnightcore\b", re.IGNORECASE)
_SPACE_RE = re.compile(r"\s+")
_BANNED_WORDS = {
    "official",
    "video",
    "live",
    "lyrics",
    "lyric",
    "amv",
    "animated",
    "op",
    "ed",
    "opening",
    "ending",
    "singles",
    "unknown",
    "misc",
    "general",
    "collection",
    "collections",
    "youtube",
}


def normalize_key(value: Any) -> str:
    return _SPACE_RE.sub(" ", str(value or "").strip().lower())


def _title_case(value: str) -> str:
    return " ".join(part.capitalize() for part in normalize_key(value).split())


def _text_blob(track: dict[str, Any]) -> str:
    profile = track.get("semantic_profile") or {}
    pieces = [
        track.get("title"),
        track.get("source_title"),
        track.get("sourceTitle"),
        track.get("style"),
        " ".join(str(tag) for tag in track.get("tags") or []),
        " ".join(str(marker) for marker in profile.get("style_markers") or []),
        " ".join(str(marker) for marker in profile.get("context_markers") or []),
        str(profile.get("likely_group_theme") or profile.get("theme") or ""),
    ]
    return " ".join(str(piece or "") for piece in pieces)


def has_nightcore_evidence(track: dict[str, Any]) -> bool:
    style = normalize_key(track.get("style"))
    tags = {normalize_key(tag) for tag in track.get("tags") or []}
    if style == "nightcore" or "nightcore" in tags:
        return True
    return bool(_NIGHTCORE_RE.search(_text_blob(track)))


def _profile_for_track(track: dict[str, Any]) -> dict[str, Any]:
    profile = dict(track.get("semantic_profile") or {})
    genre = normalize_genre(profile.get("main_genre") or profile.get("broad_genre") or track.get("genre"))
    if genre == UNKNOWN_GENRE:
        genre = normalize_genre(track.get("genre"))
    profile.setdefault("main_genre", genre)
    profile.setdefault("broad_genre", genre)
    profile.setdefault("style_markers", [])
    profile.setdefault("context_markers", [])
    profile.setdefault("performance_type", "studio")
    profile.setdefault("likely_group_theme", "")
    profile.setdefault("theme", profile.get("likely_group_theme") or "")
    return profile


def fallback_group_for_track(track: dict[str, Any]) -> str:
    profile = _profile_for_track(track)
    if has_nightcore_evidence(track):
        return "Nightcore"
    if normalize_key(profile.get("main_genre")) == "soundtrack" or normalize_key(profile.get("broad_genre")) == "soundtrack":
        return "Anime Soundtracks"
    return build_group_name_from_cluster([profile])


def _words_in_text(value: str) -> set[str]:
    return set(normalize_key(value).split())


def _signal_group_from_candidate(candidate: str, *, track: dict[str, Any]) -> str:
    profile = _profile_for_track(track)
    styles = {normalize_key(item) for item in profile.get("style_markers") or []}
    contexts = {normalize_key(item) for item in profile.get("context_markers") or []}
    context_words = _words_in_text(" ".join(contexts))
    text_words = _words_in_text(_text_blob(track))
    genre_keys = {normalize_key(profile.get("main_genre")), normalize_key(profile.get("broad_genre"))}

    has_piano = "piano" in styles or "piano" in text_words
    has_anime_context = bool(context_words & {"anime", "soundtrack", "ost", "amv"})
    has_anime_marker = bool(text_words & {"anime", "op", "ed", "opening", "ending", "amv", "ost"})
    has_soundtrack = "soundtrack" in genre_keys or "soundtrack" in text_words

    if has_piano and (has_anime_context or has_anime_marker or has_soundtrack):
        return "Anime Piano"
    if has_piano:
        return "Piano Covers"
    if has_anime_context or has_anime_marker or has_soundtrack:
        return "Anime Soundtracks"
    return ""


def normalize_library_group_candidate(candidate: str, *, track: dict[str, Any]) -> str:
    if has_nightcore_evidence(track):
        return "Nightcore"

    fallback = fallback_group_for_track(track)
    cleaned = normalize_key(candidate)
    words = cleaned.split()
    artist = normalize_key(track.get("artist"))
    title = normalize_key(track.get("title"))
    signal_group = _signal_group_from_candidate(candidate, track=track)

    if signal_group:
        return signal_group
    if not cleaned or len(words) > 3:
        return fallback
    if set(words) & _BANNED_WORDS:
        return fallback
    if artist and artist in cleaned:
        return fallback
    if title and title in cleaned:
        return fallback
    if cleaned != normalize_key(fallback):
        return fallback
    return _title_case(cleaned)


def infer_library_group(track: dict[str, Any]) -> dict[str, Any]:
    group = normalize_library_group_candidate(fallback_group_for_track(track), track=track)
    return {
        "library_group": group,
        "library_group_source": "deterministic" if group == "Nightcore" else "local_ai",
        "library_group_confidence": 0.9 if group == "Nightcore" else float(track.get("classification_confidence") or 0.6),
    }


def apply_artist_dominant_groups(
    assignments: dict[str, dict[str, Any]], tracks_by_key: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    by_artist: dict[str, Counter[str]] = defaultdict(Counter)
    for key, assignment in assignments.items():
        track = tracks_by_key[key]
        artist = normalize_key(track.get("artist"))
        group = str(assignment.get("library_group") or "")
        if artist and group and group != "Nightcore":
            by_artist[artist][group] += 1

    dominant: dict[str, str] = {}
    for artist, counter in by_artist.items():
        total = sum(counter.values())
        if not total:
            continue
        group, count = sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0]
        if count > total / 2:
            dominant[artist] = group
    merged: dict[str, dict[str, Any]] = {}
    for key, assignment in assignments.items():
        track = tracks_by_key[key]
        artist = normalize_key(track.get("artist"))
        group = str(assignment.get("library_group") or "")
        if group != "Nightcore" and artist in dominant and _is_weak_or_context_group(group):
            merged[key] = {**assignment, "library_group": dominant[artist], "library_group_source": "artist_dominant"}
        else:
            merged[key] = dict(assignment)
    return merged


def _is_weak_or_context_group(group: str) -> bool:
    words = set(normalize_key(group).split())
    return bool(words & {"live", "video", "lyrics", "amv", "electronic", "unknown", "music"})
