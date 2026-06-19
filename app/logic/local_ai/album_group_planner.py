from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib import error, request

from app.logic.local_ai.album_group_registry import (
    load_registry,
    registry_group_for_track,
    save_registry,
    stable_group_id,
    upsert_group,
)
from app.logic.local_ai.album_group_validator import (
    build_deterministic_group_name,
    is_official_or_existing_album,
    is_repairable_source_album_folder,
    validate_group_name,
)
from app.logic.local_ai.classifier_base import CLASSIFIER_VERSION
from app.logic.local_ai.config import LocalAIConfig
from app.logic.local_ai.metadata_normalizer import normalize_artist
from app.logic.local_ai.semantic_profile import grouping_fingerprint, semantic_fingerprint
from app.logic.jellyfin_library import sanitize_component

_GROUPING_PROMPT = """You plan library album groups for one artist in a local music library.

Artist: {artist}

Tracks (stable order):
{tracks_json}

Return strict JSON only:
{{
  "groups": [
    {{
      "group_id": "short-stable-id",
      "name": "Natural human-readable group name",
      "artist_scope": "{artist}",
      "reason": "short evidence-based reason",
      "track_paths": ["absolute/path.mp3"]
    }}
  ]
}}

Rules:
1. Create as many groups as needed. No fixed bucket list.
2. Group names must be short (2-5 words), human-readable, and musically sensible.
3. Do not invent official album/release names without source evidence.
4. Do not use: Singles, Unknown Album, Misc, General, Music, Collection, or similar generic buckets.
5. Live tracks stay in the same genre/style group when musically similar; live is not a separate album by default.
6. Same input must always return the same JSON and grouping.
7. Every listed track path must appear in exactly one group.
8. Use only the provided track paths.
"""


def _normalize_key(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def track_sort_key(track: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        _normalize_key(normalize_artist(track.get("artist"))),
        _normalize_key(track.get("title")),
        _normalize_key(track.get("videoId") or track.get("video_id")),
        _normalize_key(track.get("path") or track.get("file_path")),
    )


def sort_tracks_stable(tracks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(tracks, key=track_sort_key)


def track_key(track: dict[str, Any]) -> str:
    path = track.get("path") or track.get("file_path") or ""
    mtime = track.get("fileMtime") or ""
    size = track.get("fileSize") or ""
    return f"{path}|{mtime}|{size}"


def _extract_json_object(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _call_ollama_grouping(*, base_url: str, model: str, prompt: str, timeout_seconds: int) -> dict[str, Any] | None:
    payload_data = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0, "top_p": 0.1, "seed": 42},
    }
    payload = json.dumps(payload_data).encode("utf-8")
    req = request.Request(
        f"{base_url.rstrip('/')}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout_seconds) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (error.HTTPError, error.URLError, TimeoutError, RuntimeError):
        return None
    message = body.get("message") if isinstance(body.get("message"), dict) else {}
    content = str(message.get("content") or body.get("thinking") or "").strip()
    return _extract_json_object(content)


def _cluster_tracks_by_theme(tracks: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for track in tracks:
        profile = track.get("semantic_profile") or {}
        key = grouping_fingerprint(profile) or "library tracks"
        clusters[key].append(track)
    return dict(clusters)


def _build_group_name_for_cluster(
    tracks: list[dict[str, Any]],
    *,
    model_name: str | None = None,
    artist: str | None = None,
) -> tuple[str, str]:
    representative = tracks[0]
    profile = representative.get("semantic_profile") or {}
    artist_name = normalize_artist(representative.get("artist"))
    if model_name:
        validated = validate_group_name(
            model_name,
            profile=profile,
            track=representative,
            artist=artist or artist_name,
        )
        reason = f"Grouped by {profile.get('likely_group_theme') or 'shared metadata'}."
        return validated, reason
    name = build_deterministic_group_name(profile)
    reason = f"Deterministic group from semantic profile: {profile.get('likely_group_theme') or 'shared metadata'}."
    return name, reason


def _plan_artist_groups_deterministic(artist: str, tracks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for theme, cluster in sorted(_cluster_tracks_by_theme(tracks).items(), key=lambda item: item[0]):
        member_keys = [track_key(track) for track in cluster]
        member_paths = [str(track.get("path") or "") for track in cluster if track.get("path")]
        group_name, reason = _build_group_name_for_cluster(cluster)
        group_id = stable_group_id(artist_scope=artist, group_name=group_name, member_track_keys=member_keys)
        groups.append(
            {
                "group_id": group_id,
                "name": group_name,
                "artist_scope": artist,
                "reason": reason,
                "track_paths": member_paths,
                "track_keys": member_keys,
                "semantic_fingerprint": theme,
            }
        )
    return groups


def _plan_artist_groups_with_ollama(
    artist: str,
    tracks: list[dict[str, Any]],
    *,
    config: LocalAIConfig,
) -> list[dict[str, Any]] | None:
    payload_tracks = [
        {
            "path": track.get("path"),
            "title": track.get("title"),
            "genre": track.get("genre"),
            "style": track.get("style"),
            "tags": track.get("tags") or [],
            "semantic_profile": track.get("semantic_profile") or {},
        }
        for track in tracks
    ]
    prompt = _GROUPING_PROMPT.format(
        artist=artist,
        tracks_json=json.dumps(payload_tracks, ensure_ascii=False, indent=2, sort_keys=True),
    )
    parsed = _call_ollama_grouping(
        base_url=config.ollama_url,
        model=config.model,
        prompt=prompt,
        timeout_seconds=config.timeout_seconds,
    )
    if not parsed or not isinstance(parsed.get("groups"), list):
        return None

    path_lookup = {str(track.get("path") or ""): track for track in tracks}
    groups: list[dict[str, Any]] = []
    for raw_group in parsed["groups"]:
        if not isinstance(raw_group, dict):
            continue
        member_paths = [str(path) for path in (raw_group.get("track_paths") or []) if str(path) in path_lookup]
        if not member_paths:
            continue
        cluster = [path_lookup[path] for path in member_paths]
        member_keys = [track_key(track) for track in cluster]
        group_name, reason = _build_group_name_for_cluster(
            cluster,
            model_name=str(raw_group.get("name") or "").strip() or None,
            artist=artist,
        )
        group_id = stable_group_id(artist_scope=artist, group_name=group_name, member_track_keys=member_keys)
        groups.append(
            {
                "group_id": group_id,
                "name": group_name,
                "artist_scope": artist,
                "reason": str(raw_group.get("reason") or reason).strip() or reason,
                "track_paths": member_paths,
                "track_keys": member_keys,
                "semantic_fingerprint": semantic_fingerprint(cluster[0].get("semantic_profile") or {}),
            }
        )
    if len({path for group in groups for path in group["track_paths"]}) != len(tracks):
        return None
    return groups


def plan_library_album_groups(
    tracks: list[dict[str, Any]],
    *,
    config: LocalAIConfig,
    rebuild: bool = False,
    repair_managed_albums: bool = False,
    use_local_ai: bool = False,
    persist_registry: bool = True,
) -> dict[str, Any]:
    sorted_tracks = sort_tracks_stable(tracks)
    registry = load_registry(config.album_groups_registry_path)
    if rebuild:
        registry = {"groups": {}, "track_assignments": {}}

    assignments: dict[str, dict[str, Any]] = {}
    groups_out: list[dict[str, Any]] = []
    move_plans: list[dict[str, str]] = []

    by_artist: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for track in sorted_tracks:
        artist = normalize_artist(track.get("artist"))
        existing_album = track.get("album") or ""
        if is_official_or_existing_album(existing_album, track=track) and not repair_managed_albums:
            key = track_key(track)
            assignments[key] = {
                "album": existing_album,
                "album_kind": "official_or_existing",
                "album_source": "existing",
                "album_confidence": 1.0,
                "group_id": None,
                "collection": track.get("collection"),
            }
            continue
        by_artist[artist].append(track)

    for artist in sorted(by_artist):
        artist_tracks = by_artist[artist]
        if not rebuild:
            preserved: list[dict[str, Any]] = []
            pending: list[dict[str, Any]] = []
            for track in artist_tracks:
                key = track_key(track)
                existing_group = registry_group_for_track(registry, key)
                if existing_group and existing_group.get("classifier_version") == CLASSIFIER_VERSION:
                    group_name = str(existing_group.get("group_name") or "")
                    assignments[key] = {
                        "album": group_name,
                        "album_kind": "inferred_library_group",
                        "album_source": "registry",
                        "album_confidence": 0.9,
                        "group_id": existing_group.get("group_id"),
                        "collection": _live_collection_for_track(track),
                    }
                    groups_out.append(
                        {
                            "group_id": existing_group.get("group_id"),
                            "name": group_name,
                            "artist_scope": artist,
                            "reason": "Loaded from stable album group registry.",
                            "track_paths": list(existing_group.get("member_paths") or []),
                            "track_keys": list(existing_group.get("member_track_keys") or []),
                            "semantic_fingerprint": existing_group.get("semantic_fingerprint"),
                        }
                    )
                    preserved.append(track)
                else:
                    pending.append(track)
            artist_tracks = pending

        if not artist_tracks:
            continue

        planned_groups = None
        if use_local_ai and config.metadata_enabled and config.provider == "ollama" and config.model:
            planned_groups = _plan_artist_groups_with_ollama(artist, artist_tracks, config=config)
        if not planned_groups:
            planned_groups = _plan_artist_groups_deterministic(artist, artist_tracks)

        for group in planned_groups:
            groups_out.append(group)
            for track in artist_tracks:
                path = str(track.get("path") or "")
                if path not in group["track_paths"]:
                    continue
                key = track_key(track)
                assignments[key] = {
                    "album": group["name"],
                    "album_kind": "inferred_library_group",
                    "album_source": "local_ai",
                    "album_confidence": 0.8,
                    "group_id": group["group_id"],
                    "collection": _live_collection_for_track(track),
                }
            if persist_registry:
                upsert_group(
                    registry,
                    group_id=group["group_id"],
                    group_name=group["name"],
                    artist_scope=artist,
                    semantic_fingerprint=group["semantic_fingerprint"],
                    member_track_keys=group["track_keys"],
                    member_paths=group["track_paths"],
                    model=config.model if use_local_ai else "",
                )

    if persist_registry:
        save_registry(config.album_groups_registry_path, registry, model=config.model if use_local_ai else "")

    return {
        "classifier_version": CLASSIFIER_VERSION,
        "groups": groups_out,
        "assignments": assignments,
        "move_plans": move_plans,
    }


def _live_collection_for_track(track: dict[str, Any]) -> str | None:
    profile = track.get("semantic_profile") or {}
    if _normalize_key(profile.get("performance_type")) == "live":
        return "Live"
    style = _normalize_key(track.get("style"))
    tags = {_normalize_key(tag) for tag in (track.get("tags") or [])}
    if style == "live" or "live" in tags:
        return "Live"
    return track.get("collection")


def apply_album_group_assignments(track: dict[str, Any], assignment: dict[str, Any] | None) -> dict[str, Any]:
    enriched = dict(track)
    if not assignment:
        return enriched
    enriched["album"] = assignment["album"]
    enriched["album_kind"] = assignment["album_kind"]
    enriched["album_source"] = assignment["album_source"]
    enriched["album_confidence"] = assignment["album_confidence"]
    enriched["group_id"] = assignment.get("group_id")
    if assignment.get("collection") is not None:
        enriched["collection"] = assignment["collection"]
    return enriched


def build_move_plans_for_assignments(
    tracks: list[dict[str, Any]],
    assignments: dict[str, dict[str, Any]],
    *,
    music_dir: str,
) -> list[dict[str, str]]:
    from app.logic.local_ai.enrichment_service import plan_track_album_move

    plans: list[dict[str, str]] = []
    for track in sort_tracks_stable(tracks):
        path = str(track.get("path") or "")
        if not path:
            continue
        assignment = assignments.get(track_key(track))
        if not assignment:
            continue
        if assignment.get("album_kind") == "official_or_existing":
            continue
        target_album = str(assignment.get("album") or "")
        artist = normalize_artist(track.get("artist"))
        current_album = sanitize_component(str(track.get("album") or ""))
        parent_album = sanitize_component(str(Path(path).parent.name)) if path else ""
        needs_move = is_repairable_source_album_folder(parent_album) or (
            parent_album and parent_album != sanitize_component(target_album)
        )
        if not needs_move:
            continue
        plan = plan_track_album_move(path=path, artist=artist, target_album=target_album, music_dir=music_dir)
        if plan:
            plans.append(plan)
    return plans


def format_album_group_plan(plan: dict[str, Any], *, move_plans: list[dict[str, str]] | None = None) -> str:
    lines: list[str] = []
    move_lookup: dict[str, list[dict[str, str]]] = defaultdict(list)
    for move in move_plans or []:
        move_lookup[str(move.get("artist") or "")].append(move)

    for group in plan.get("groups", []):
        lines.append(f"Artist: {group.get('artist_scope')}")
        lines.append(f"Group: {group.get('name')}")
        lines.append(f"Reason: {group.get('reason')}")
        lines.append("Tracks:")
        for path in group.get("track_paths", []):
            lines.append(f"  - {path}")
        artist_moves = move_lookup.get(str(group.get("artist_scope") or ""), [])
        if artist_moves:
            lines.append("Moves:")
            for move in artist_moves:
                if move.get("from") in group.get("track_paths", []):
                    lines.append(f"  from: {move.get('from')}")
                    lines.append(f"  to: {move.get('to')}")
        lines.append("")
    return "\n".join(lines).strip()
