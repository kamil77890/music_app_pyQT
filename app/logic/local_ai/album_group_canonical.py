from __future__ import annotations

import re
from collections import Counter
from typing import Any

from app.logic.local_ai.metadata_normalizer import UNKNOWN_GENRE, normalize_genre

_MAX_GROUP_NAME_WORDS = 3
_MEDIUM_TOKENS = frozenset(
    {
        "live",
        "official",
        "video",
        "music",
        "lyrics",
        "lyric",
        "amv",
        "animated",
        "mv",
        "op",
        "ed",
        "opening",
        "ending",
        "studio",
        "remix",
        "version",
        "versions",
        "tracks",
        "track",
        "collection",
        "collections",
        "arr",
        "arrangement",
    }
)
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
_FRANCHISE_STYLE_PATTERN = re.compile(
    r"\b(cyberpunk|tokyo ghoul|solo leveling|eminence|beethoven|edgerunners|ghoul)\b",
    re.IGNORECASE,
)


def _normalize_key(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _title_case_phrase(value: str) -> str:
    return " ".join(part.capitalize() for part in value.split())


def _dominant(counter: Counter[str]) -> str:
    if not counter:
        return ""
    return counter.most_common(1)[0][0]


def _normalized_context_keys(profile: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for marker in profile.get("context_markers") or []:
        key = _normalize_key(marker)
        if "anime" in key:
            keys.add("anime")
        if "soundtrack" in key or "ost" in key or "amv" in key:
            keys.add("soundtrack")
        if key in {"music video", "mv"} or "music video" in key:
            keys.add("music video")
    return keys


def aggregate_cluster_signals(profiles: list[dict[str, Any]]) -> dict[str, Any]:
    style_counter: Counter[str] = Counter()
    context_counter: Counter[str] = Counter()
    genre_counter: Counter[str] = Counter()
    performance_counter: Counter[str] = Counter()

    for profile in profiles:
        genre = _normalize_key(profile.get("main_genre") or profile.get("broad_genre") or UNKNOWN_GENRE)
        if genre and genre != _normalize_key(UNKNOWN_GENRE):
            genre_counter[genre] += 1
        for marker in profile.get("style_markers") or []:
            key = _normalize_key(marker)
            if key and key not in _MEDIUM_TOKENS:
                style_counter[key] += 1
        for marker_key in _normalized_context_keys(profile):
            if marker_key in {"music video"}:
                continue
            context_counter[marker_key] += 1
        perf = _normalize_key(profile.get("performance_type") or "")
        if perf:
            performance_counter[perf] += 1

    return {
        "styles": style_counter,
        "contexts": context_counter,
        "genres": genre_counter,
        "performances": performance_counter,
        "track_count": len(profiles),
    }


def broad_cluster_key(profile: dict[str, Any]) -> str:
    styles = {_normalize_key(item) for item in (profile.get("style_markers") or [])}
    contexts = _normalized_context_keys(profile)
    genre = _normalize_key(profile.get("main_genre") or profile.get("broad_genre") or "")

    if "piano" in styles and ({"anime", "soundtrack"} & contexts):
        return "anime_piano"
    if "nightcore" in styles:
        return "nightcore"
    if "piano" in styles and "classical" in styles:
        return "classical_piano"
    if "piano" in styles:
        return "piano_covers"
    if {"anime", "soundtrack"} & contexts:
        return "anime_soundtracks"
    if genre in {"rock", "metal"} or "rock" in styles or "alternative" in styles:
        if "pop" in styles or genre == "pop":
            return "pop_rock"
        return "alternative_rock"
    if genre == "pop" or "pop" in styles:
        return "pop"
    if genre in {"electronic", "dance"} or "electronic" in styles or "dance" in styles:
        return "electronic"
    if genre == "classical" or "classical" in styles:
        return "classical_piano"
    if genre == "soundtrack":
        return "anime_soundtracks"
    if genre and genre != _normalize_key(UNKNOWN_GENRE):
        return genre
    return "library"


def canonical_cluster_key(profile: dict[str, Any]) -> str:
    return broad_cluster_key(profile)


def build_group_name_from_cluster(profiles: list[dict[str, Any]]) -> str:
    if not profiles:
        return "Library"

    signals = aggregate_cluster_signals(profiles)
    styles = signals["styles"]
    contexts = signals["contexts"]
    genres = signals["genres"]
    count = max(signals["track_count"], 1)

    if styles.get("piano", 0) >= count * 0.34 and (
        contexts.get("anime", 0) + contexts.get("soundtrack", 0) >= count * 0.34
    ):
        return "Anime Piano"
    if styles.get("nightcore", 0) >= count * 0.34:
        return "Nightcore"
    if styles.get("piano", 0) >= count * 0.34:
        if styles.get("classical", 0) > 0:
            return "Classical Piano"
        return "Piano Covers"
    if contexts.get("anime", 0) + contexts.get("soundtrack", 0) >= count * 0.34:
        return "Anime Soundtracks"
    rock_signals = genres.get("rock", 0) + styles.get("rock", 0)
    electronic_signals = (
        genres.get("electronic", 0) + genres.get("dance", 0) + styles.get("electronic", 0) + styles.get("dance", 0)
    )
    if rock_signals >= 1 and styles.get("nightcore", 0) < count * 0.34:
        if rock_signals >= count * 0.34 or (rock_signals >= 1 and electronic_signals > 0):
            if styles.get("pop", 0) > 0 or genres.get("pop", 0) > 0:
                return "Pop Rock"
            return "Alternative Rock"
    if genres.get("rock", 0) + styles.get("rock", 0) >= count * 0.34:
        if styles.get("pop", 0) > 0 or genres.get("pop", 0) > 0:
            return "Pop Rock"
        return "Alternative Rock"
    if genres.get("pop", 0) + styles.get("pop", 0) >= count * 0.34:
        return "Pop"
    if genres.get("electronic", 0) + genres.get("dance", 0) + styles.get("electronic", 0) >= count * 0.34:
        return "Electronic"

    dominant_genre = _dominant(genres)
    dominant_style = _dominant(styles)
    if dominant_style and dominant_genre and dominant_style != dominant_genre:
        return _title_case_phrase(f"{dominant_style} {_dominant(genres)}")
    if dominant_style:
        return _title_case_phrase(dominant_style)
    if dominant_genre:
        return _title_case_phrase(dominant_genre)
    return "Library"


def _strip_medium_tokens(name: str) -> str:
    words = [word for word in _normalize_key(name).split() if word not in _MEDIUM_TOKENS and word not in _BANNED_GROUP_WORDS]
    return " ".join(words).strip()


def canonicalize_group_name(name: str, profiles: list[dict[str, Any]]) -> str:
    rebuilt = build_group_name_from_cluster(profiles)
    stripped = _strip_medium_tokens(name)
    candidate = rebuilt

    if stripped:
        stripped_words = stripped.split()
        if len(stripped_words) <= _MAX_GROUP_NAME_WORDS:
            stripped_title = _title_case_phrase(stripped)
            if not is_weak_group_name(stripped_title, profiles=profiles):
                candidate = stripped_title

    if _FRANCHISE_STYLE_PATTERN.search(candidate):
        candidate = rebuilt
    if is_weak_group_name(candidate, profiles=profiles):
        candidate = rebuilt
    return candidate or rebuilt


def is_weak_group_name(name: str, *, profiles: list[dict[str, Any]] | None = None, artist: str | None = None) -> bool:
    cleaned = _normalize_key(name)
    if not cleaned:
        return True
    if set(cleaned.split()) & _BANNED_GROUP_WORDS:
        return True
    words = cleaned.split()
    if len(words) > _MAX_GROUP_NAME_WORDS:
        return True
    if artist and cleaned == _normalize_key(artist):
        return True
    if artist and cleaned.endswith(_normalize_key(artist)):
        return True
    medium_hits = sum(1 for word in words if word in _MEDIUM_TOKENS)
    if medium_hits >= 2:
        return True
    if medium_hits == 1 and len(words) <= 2 and words[0] in _MEDIUM_TOKENS:
        return True
    if _FRANCHISE_STYLE_PATTERN.search(cleaned) and len(words) >= 2:
        return True
    if profiles:
        cluster_name = _normalize_key(build_group_name_from_cluster(profiles))
        if cluster_name and cleaned != cluster_name and len(words) >= 3:
            return True
    return False


def merge_minority_single_track_groups(groups: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    if len(groups) <= 1:
        return groups, []

    ordered = sorted(groups, key=lambda group: len(group.get("track_paths") or []), reverse=True)
    merge_log: list[dict[str, str]] = []
    dominant = ordered[0]
    merged_groups = [dominant]
    dominant_profiles = list(dominant.get("profiles") or [])
    dominant_paths = list(dominant.get("track_paths") or [])
    dominant_keys = list(dominant.get("track_keys") or [])
    merged_names = [str(dominant.get("name") or "")]

    for group in ordered[1:]:
        track_count = len(group.get("track_paths") or [])
        if track_count == 1 and len(dominant.get("track_paths") or []) >= 2:
            dominant_profiles.extend(group.get("profiles") or [])
            dominant_paths.extend(group.get("track_paths") or [])
            dominant_keys.extend(group.get("track_keys") or [])
            merged_names.append(str(group.get("name") or ""))
            merge_log.append(
                {
                    "artist_scope": str(group.get("artist_scope") or ""),
                    "merged_from": str(group.get("name") or ""),
                    "merged_to": str(dominant.get("name") or ""),
                    "cluster_key": "minority_single_track_merge",
                }
            )
            continue
        merged_groups.append(group)

    if len(merged_names) > 1:
        final_name = canonicalize_group_name(build_group_name_from_cluster(dominant_profiles), dominant_profiles)
        dominant_paths = sorted(dict.fromkeys(dominant_paths))
        dominant_keys = sorted(dict.fromkeys(dominant_keys))
        merged_groups[0] = {
            **dominant,
            "name": final_name,
            "profiles": dominant_profiles,
            "track_paths": dominant_paths,
            "track_keys": dominant_keys,
            "merge_from": merged_names,
            "reason": "Merged a single outlier track into the dominant artist group.",
        }
        if merge_log:
            merge_log[-1]["merged_to"] = final_name

    return merged_groups, merge_log


def merge_groups_by_canonical_key(groups: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    merge_log: list[dict[str, str]] = []

    for group in groups:
        profiles = group.get("profiles") or []
        if not profiles and group.get("track_paths"):
            profiles = [{} for _ in group["track_paths"]]
        key = canonical_cluster_key(profiles[0]) if profiles else _normalize_key(group.get("name") or "library")
        buckets.setdefault(key, []).append(group)

    merged: list[dict[str, Any]] = []
    for key, bucket in sorted(buckets.items()):
        if len(bucket) == 1:
            merged.append(bucket[0])
            continue
        combined_profiles: list[dict[str, Any]] = []
        combined_paths: list[str] = []
        combined_keys: list[str] = []
        old_names = []
        for group in bucket:
            combined_profiles.extend(group.get("profiles") or [])
            combined_paths.extend(group.get("track_paths") or [])
            combined_keys.extend(group.get("track_keys") or [])
            old_names.append(str(group.get("name") or ""))
        combined_paths = sorted(dict.fromkeys(combined_paths))
        combined_keys = sorted(dict.fromkeys(combined_keys))
        final_name = canonicalize_group_name(build_group_name_from_cluster(combined_profiles), combined_profiles)
        merge_log.append(
            {
                "artist_scope": str(bucket[0].get("artist_scope") or ""),
                "merged_from": " + ".join(old_names),
                "merged_to": final_name,
                "cluster_key": key,
            }
        )
        merged.append(
            {
                **bucket[0],
                "name": final_name,
                "reason": f"Merged {len(bucket)} similar groups into one coherent library group.",
                "track_paths": combined_paths,
                "track_keys": combined_keys,
                "profiles": combined_profiles,
                "semantic_fingerprint": key,
                "merge_from": old_names,
            }
        )
    return merged, merge_log


def finalize_artist_groups(artist: str, groups: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    merged, merge_log = merge_groups_by_canonical_key(groups)
    merged, minority_log = merge_minority_single_track_groups(merged)
    return merged, merge_log + minority_log
