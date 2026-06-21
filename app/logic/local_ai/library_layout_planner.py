from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.logic.jellyfin_library import sanitize_component
from app.logic.local_ai.classifier_base import CLASSIFIER_VERSION
from app.logic.local_ai.config import LocalAIConfig
from app.logic.local_ai.library_group_rules import (
    GROUPING_CONFIG_VERSION,
    apply_artist_dominant_groups,
    infer_library_group,
    normalize_key,
)

PLAN_DIR = Path("data/library_layout_plans")
MANIFEST_DIR = Path("data/library_layout_apply_manifests")
_PLAN_ID_RE = re.compile(r"^[0-9a-f]{16}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def track_key(track: dict[str, Any]) -> str:
    return "|".join(
        str(part or "")
        for part in (
            track.get("path") or track.get("file_path"),
            track.get("fileMtime"),
            track.get("fileSize"),
            track.get("videoId") or track.get("video_id"),
        )
    )


def track_fingerprint(track: dict[str, Any]) -> dict[str, Any]:
    path = str(track.get("path") or track.get("file_path") or "")
    stat = os.stat(path) if path and os.path.exists(path) else None
    return {
        "source_path": path,
        "resolved_source_path": str(Path(path).resolve()) if path else "",
        "mtime": stat.st_mtime_ns if stat else track.get("fileMtime"),
        "size": stat.st_size if stat else track.get("fileSize"),
        "track_key": track_key(track),
        "videoId": str(track.get("videoId") or track.get("video_id") or ""),
    }


def _source_path(track: dict[str, Any]) -> str:
    return str(track.get("path") or track.get("file_path") or "")


def _safe_layout_path(music_dir: str, *parts: str) -> Path:
    root = Path(music_dir).resolve()
    safe_parts = [sanitize_component(part) for part in parts[:-1]]
    safe_parts.append(sanitize_component(parts[-1], max_len=220))
    destination = root.joinpath(*safe_parts).resolve(strict=False)
    if os.path.commonpath([str(root), str(destination)]) != str(root):
        raise ValueError(f"Path traversal blocked: {destination} is outside {root}")
    return destination


def _is_ai_generated_album_name(name: str) -> bool:
    known = {
        "nightcore", "anime piano", "piano covers", "anime soundtracks",
        "alternative rock", "pop rock", "pop", "electronic", "classical piano",
        "library", "anime piano covers", "rock", "metal", "dance",
        "electronic covers", "classical", "piano",
    }
    return normalize_key(name) in known


def _real_album(track: dict[str, Any]) -> str:
    album = str(track.get("album") or "").strip()
    album_kind = normalize_key(track.get("album_kind"))
    album_source = normalize_key(track.get("album_source"))
    if not album or normalize_key(album) in {"unknown album", "unknown", "singles"}:
        return ""
    if album_kind in {"inferred_library_group", "local_ai", "ai_managed", "pending_grouping"}:
        return ""
    if album_source in {"local_ai", "registry", "pending_grouping", "ai_managed"} and album_kind != "official_or_existing":
        return ""
    if _is_ai_generated_album_name(album):
        return ""
    return album


def _destination_for_track(track: dict[str, Any], assignment: dict[str, Any], *, music_dir: str) -> str:
    source = Path(_source_path(track))
    filename = source.name or sanitize_component(str(track.get("title") or "track"))
    group_name = str(assignment["library_group"])
    album = ""
    if normalize_key(group_name) != "nightcore":
        album = _real_album(track)
        if album and normalize_key(album) == normalize_key(group_name):
            album = ""
    parts = [group_name, str(track.get("artist") or "Unknown Artist").strip() or "Unknown Artist"]
    if album:
        parts.append(album)
    parts.append(filename)
    return str(_safe_layout_path(music_dir, *parts))


def stable_layout_group_id(group_name: str) -> str:
    payload = json.dumps({"group": normalize_key(group_name), "version": GROUPING_CONFIG_VERSION}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _normalized_for_hash(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "classifier_version": plan["classifier_version"],
        "model": plan["model"],
        "grouping_config_version": plan["grouping_config_version"],
        "moves": plan["moves"],
        "metadata_operations": plan["metadata_operations"],
        "fingerprints": plan["fingerprints"],
    }


def compute_plan_id(plan: dict[str, Any]) -> str:
    payload = json.dumps(_normalized_for_hash(plan), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _validate_plan_id(plan_id: Any) -> str:
    value = str(plan_id or "")
    if not _PLAN_ID_RE.fullmatch(value):
        raise ValueError("Invalid layout plan_id")
    return value


def plan_library_layout(
    tracks: list[dict[str, Any]],
    *,
    music_dir: str,
    config: LocalAIConfig,
    use_local_ai: bool = False,
) -> dict[str, Any]:
    sorted_tracks = sorted(
        tracks,
        key=lambda item: (normalize_key(item.get("artist")), normalize_key(item.get("title")), _source_path(item)),
    )
    tracks_by_key = {track_key(track): track for track in sorted_tracks}
    raw_assignments = {key: infer_library_group(track) for key, track in tracks_by_key.items()}
    assignments = apply_artist_dominant_groups(raw_assignments, tracks_by_key)

    tree_map: dict[str, dict[str, Any]] = {}
    moves: list[dict[str, Any]] = []
    metadata_ops: list[dict[str, Any]] = []
    fingerprints: list[dict[str, Any]] = []
    conflicts: list[str] = []

    for key, track in tracks_by_key.items():
        assignment = assignments[key]
        group_name = str(assignment["library_group"])
        artist = str(track.get("artist") or "Unknown Artist").strip() or "Unknown Artist"
        source = _source_path(track)

        if not group_name:
            conflicts.append({
                "type": "insufficient_library_group_evidence",
                "track_key": key,
                "path": source,
                "artist": artist,
                "title": track.get("title") or "",
                "message": f"No valid library group could be determined for track '{track.get('title') or ''}' by {artist}",
            })
            continue

        destination = _destination_for_track(track, assignment, music_dir=music_dir)

        if source and str(Path(source).resolve()) != str(Path(destination).resolve(strict=False)):
            moves.append({"track_key": key, "from": source, "to": destination, "library_group": group_name, "artist": artist})

        metadata_ops.append(
            {
                "track_key": key,
                "path": source,
                "fields": {
                    "LOCAL_AI_LIBRARY_GROUP": group_name,
                    "LOCAL_AI_GROUP_ID": stable_layout_group_id(group_name),
                    "LOCAL_AI_COLLECTION": track.get("collection") or "",
                },
            }
        )
        fingerprints.append(track_fingerprint(track))

        group_node = tree_map.setdefault(group_name, {"name": group_name, "cover": "", "artists": {}})
        artist_node = group_node["artists"].setdefault(artist, {"name": artist, "track_count": 0, "tracks": []})
        artist_node["track_count"] += 1
        artist_node["tracks"].append({"title": track.get("title") or "", "path": source, "track_key": key})

    tree: list[dict[str, Any]] = []
    for group_name in sorted(tree_map, key=normalize_key):
        group = tree_map[group_name]
        artists = [group["artists"][name] for name in sorted(group["artists"], key=normalize_key)]
        for artist in artists:
            artist["tracks"] = sorted(
                artist["tracks"],
                key=lambda item: (normalize_key(item.get("title")), str(item.get("path") or ""), str(item.get("track_key") or "")),
            )
        tree.append({"name": group["name"], "cover": group["cover"], "artists": artists})

    plan = {
        "plan_id": "",
        "generated_at": utc_now(),
        "classifier_version": CLASSIFIER_VERSION,
        "model": config.model if use_local_ai else "",
        "grouping_config_version": GROUPING_CONFIG_VERSION,
        "library_root": str(Path(music_dir).resolve()),
        "tree": tree,
        "moves": sorted(moves, key=lambda item: (item["to"], item["from"])),
        "metadata_operations": sorted(metadata_ops, key=lambda item: item["track_key"]),
        "fingerprints": sorted(fingerprints, key=lambda item: item["track_key"]),
        "conflicts": sorted(conflicts, key=lambda item: (item.get("artist", ""), item.get("track_key", ""))),
    }
    plan["plan_id"] = compute_plan_id(plan)
    return plan


def save_layout_plan(plan: dict[str, Any], *, plan_dir: Path = PLAN_DIR) -> Path:
    plan_id = _validate_plan_id(plan.get("plan_id"))
    plan_dir.mkdir(parents=True, exist_ok=True)
    path = plan_dir / f"{plan_id}.json"
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _load_plan_file(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
        return json.loads(text)
    except FileNotFoundError:
        raise ValueError(f"plan file not found: {path}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed plan file (JSON decode error): {exc}")
    except OSError as exc:
        raise ValueError(f"plan file read error: {exc}")


def load_layout_plan(plan_id: str, *, plan_dir: Path = PLAN_DIR) -> dict[str, Any]:
    path = plan_dir / f"{_validate_plan_id(plan_id)}.json"
    return _load_plan_file(path)


def _fingerprint_matches(expected: dict[str, Any], *, track_key_value: str = "", operation_source: str = "") -> tuple[bool, str]:
    if not expected:
        return False, "missing fingerprint"
    if track_key_value and str(expected.get("track_key") or "") != track_key_value:
        return False, "track_key fingerprint mismatch"
    expected_video_id = str(expected.get("videoId") or "")
    if expected_video_id:
        key_video_id = str(track_key_value or expected.get("track_key") or "").rsplit("|", 1)[-1]
        if key_video_id != expected_video_id:
            return False, "videoId fingerprint mismatch"
    source = str(expected.get("source_path") or "")
    if not source or not os.path.isfile(source):
        return False, "source missing"
    resolved = str(Path(source).resolve())
    if resolved != str(expected.get("resolved_source_path") or ""):
        return False, "resolved source path changed"
    if operation_source and str(Path(operation_source).resolve()) != resolved:
        return False, "operation source differs from fingerprint"
    stat = os.stat(source)
    if stat.st_mtime_ns != expected.get("mtime"):
        return False, "mtime fingerprint mismatch"
    if stat.st_size != expected.get("size"):
        return False, "size fingerprint mismatch"
    return True, ""


def _resolve_duplicate(path: Path) -> Path:
    if not path.exists():
        return path
    parent = path.parent
    stem = path.stem
    suffix = path.suffix
    counter = 1
    while True:
        candidate = parent / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def _within_root(path: Path, root: Path) -> bool:
    try:
        resolved = path.resolve(strict=False)
        return os.path.commonpath([str(root), str(resolved)]) == str(root)
    except ValueError:
        return False


def choose_cover_operations(source_covers: list[str], *, destination_dir: str) -> list[dict[str, str]]:
    destination = Path(destination_dir) / "cover.jpg"
    operations: list[dict[str, str]] = []
    for index, source in enumerate(sorted(source_covers, key=lambda value: (normalize_key(value), value))):
        if destination.exists():
            operations.append({"from": source, "to": str(destination), "status": "skipped", "error": "destination cover exists"})
        elif index == 0:
            operations.append({"from": source, "to": str(destination), "status": "planned", "error": ""})
        else:
            operations.append({"from": source, "to": str(destination), "status": "skipped", "error": "non-representative cover"})
    return operations


def _write_manifest(entries: list[dict[str, Any]], *, manifest_dir: Path, plan_id: str) -> Path:
    manifest_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    path = manifest_dir / f"{_validate_plan_id(plan_id)}-{timestamp}.json"
    payload = {"plan_id": plan_id, "entries": entries}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _manifest_entry(plan_id: str, track_key_value: str, from_path: str, to_path: str) -> dict[str, Any]:
    return {
        "plan_id": plan_id,
        "track_key": track_key_value,
        "from": from_path,
        "to": to_path,
        "timestamp": utc_now(),
        "status": "planned",
        "error": "",
        "metadata_fields_written": [],
    }


def _metadata_fields_for_writer(fields: dict[str, Any]) -> dict[str, Any]:
    return {
        "library_group": fields.get("LOCAL_AI_LIBRARY_GROUP") or "",
        "group_id": fields.get("LOCAL_AI_GROUP_ID") or "",
        "collection": fields.get("LOCAL_AI_COLLECTION") or "",
    }


def _write_metadata_if_available(path: str, fields: dict[str, Any]) -> list[str]:
    try:
        from app.logic.local_ai.enrichment_service import write_library_layout_metadata
    except ImportError:
        return []

    return list(write_library_layout_metadata(path, _metadata_fields_for_writer(fields)))


def _record_fingerprint_conflict(
    entry: dict[str, Any],
    result: dict[str, Any],
    *,
    error: str,
    fingerprint: dict[str, Any],
) -> None:
    entry["status"] = "conflict"
    entry["error"] = f"fingerprint conflict: {error}"
    entry["fingerprint"] = fingerprint
    result["conflicts"] += 1


def _record_error(entry: dict[str, Any], result: dict[str, Any], error: str) -> None:
    entry["status"] = "error"
    entry["error"] = error
    result["errors"] += 1


def _abort_apply(plan_id: str, result: dict[str, Any], *, manifest_dir: Path, message: str) -> dict[str, Any]:
    result.update({"errors": 1, "message": message})
    _write_manifest(
        [
            {
                "plan_id": plan_id,
                "track_key": "",
                "from": "",
                "to": "",
                "timestamp": utc_now(),
                "status": "error",
                "error": message,
                "metadata_fields_written": [],
            }
        ],
        manifest_dir=manifest_dir,
        plan_id=plan_id,
    )
    return result


def _plan_field_is_list_of_dicts(plan: dict[str, Any], field: str) -> bool:
    value = plan.get(field)
    return isinstance(value, list) and all(isinstance(item, dict) for item in value)


def _plan_shape_error(plan: dict[str, Any]) -> str:
    for field in ("fingerprints", "metadata_operations", "moves"):
        if not _plan_field_is_list_of_dicts(plan, field):
            return f"malformed saved plan: {field} must be a list of objects"
    for item in plan["metadata_operations"]:
        fields = item.get("fields", {})
        if fields is not None and not isinstance(fields, dict):
            return "malformed saved plan: metadata operation fields must be an object"
    return ""


def apply_library_layout_plan(
    plan_id: str,
    *,
    current_music_dir: str,
    plan_dir: Path = PLAN_DIR,
    manifest_dir: Path = MANIFEST_DIR,
) -> dict[str, Any]:
    plan_id = _validate_plan_id(plan_id)
    result = {
        "plan_id": plan_id,
        "applied": 0,
        "files_moved": 0,
        "metadata_written": 0,
        "conflicts": 0,
        "errors": 0,
        "message": "",
    }

    try:
        plan = load_layout_plan(plan_id, plan_dir=plan_dir)
    except ValueError as exc:
        return _abort_apply(plan_id, result, manifest_dir=manifest_dir, message=str(exc))

    current_root = Path(current_music_dir).resolve()

    if not isinstance(plan, dict):
        return _abort_apply(plan_id, result, manifest_dir=manifest_dir, message="malformed saved plan: root must be an object")
    if str(plan.get("plan_id") or "") != plan_id:
        return _abort_apply(plan_id, result, manifest_dir=manifest_dir, message="saved plan_id does not match requested plan_id")
    try:
        recomputed_plan_id = compute_plan_id(plan)
    except Exception as exc:
        return _abort_apply(plan_id, result, manifest_dir=manifest_dir, message=f"malformed saved plan: {exc}")
    if recomputed_plan_id != plan_id:
        return _abort_apply(plan_id, result, manifest_dir=manifest_dir, message="saved plan integrity check failed")

    shape_error = _plan_shape_error(plan)
    if shape_error:
        return _abort_apply(plan_id, result, manifest_dir=manifest_dir, message=shape_error)

    if str(plan.get("library_root") or "") != str(current_root):
        return _abort_apply(
            plan_id,
            result,
            manifest_dir=manifest_dir,
            message="plan library_root differs from current music library path",
        )

    fingerprints = {str(item.get("track_key") or ""): item for item in plan.get("fingerprints", [])}
    metadata_by_key = {str(item.get("track_key") or ""): item for item in plan.get("metadata_operations", [])}
    manifest_entries: list[dict[str, Any]] = []

    for move in plan.get("moves", []):
        key = str(move.get("track_key") or "")
        from_path = str(move.get("from") or "")
        to_path = str(move.get("to") or "")
        entry = _manifest_entry(plan_id, key, from_path, to_path)
        fingerprint = fingerprints.get(key, {})
        ok, error = _fingerprint_matches(fingerprint, track_key_value=key, operation_source=from_path)
        if ok and not _within_root(Path(from_path), current_root):
            ok, error = False, "source outside library_root"
        if ok and not _within_root(Path(to_path), current_root):
            ok, error = False, "destination outside library_root"
        if not ok:
            _record_fingerprint_conflict(entry, result, error=error, fingerprint=fingerprint)
            manifest_entries.append(entry)
            continue

        try:
            destination = _resolve_duplicate(Path(to_path))
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(from_path, str(destination))
            entry["to"] = str(destination)
            entry["status"] = "moved"
            result["files_moved"] += 1

            metadata_op = metadata_by_key.get(key)
            if metadata_op:
                fields = metadata_op.get("fields") or {}
                written = _write_metadata_if_available(str(destination), fields)
                entry["metadata_fields_written"] = written
                if written:
                    result["metadata_written"] += 1
            result["applied"] += 1
        except Exception as exc:
            _record_error(entry, result, str(exc))
        manifest_entries.append(entry)

    processed_keys = {entry["track_key"] for entry in manifest_entries}
    for key, metadata_op in metadata_by_key.items():
        if key in processed_keys:
            continue
        path = str(metadata_op.get("path") or "")
        entry = _manifest_entry(plan_id, key, path, path)
        fingerprint = fingerprints.get(key, {})
        ok, error = _fingerprint_matches(fingerprint, track_key_value=key, operation_source=path)
        if ok and not _within_root(Path(path), current_root):
            ok, error = False, "metadata path outside library_root"
        if not ok:
            _record_fingerprint_conflict(entry, result, error=error, fingerprint=fingerprint)
            manifest_entries.append(entry)
            continue

        try:
            written = _write_metadata_if_available(path, metadata_op.get("fields") or {})
            entry["metadata_fields_written"] = written
            entry["status"] = "metadata_written" if written else "metadata_skipped"
            if written:
                result["metadata_written"] += 1
                result["applied"] += 1
        except Exception as exc:
            _record_error(entry, result, str(exc))
        manifest_entries.append(entry)

    _write_manifest(manifest_entries, manifest_dir=manifest_dir, plan_id=plan_id)
    return result


def format_layout_plan_tree(plan: dict[str, Any]) -> str:
    lines = [f"Plan ID: {plan.get('plan_id')}", "Library layout tree:"]
    for group in plan.get("tree", []):
        lines.append(f"Group: {group.get('name')}")
        for artist in group.get("artists", []):
            lines.append(f"  Artist: {artist.get('name')} ({artist.get('track_count')} tracks)")
    lines.append("Conflicts:")
    if plan.get("conflicts"):
        for conflict in plan["conflicts"]:
            if isinstance(conflict, dict):
                lines.append(f"  - [{conflict.get('type', 'unknown')}] {conflict.get('message', '')}")
            else:
                lines.append(f"  - {conflict}")
    else:
        lines.append("  none")
    lines.append("Move preview:")
    if plan.get("moves"):
        for move in plan["moves"]:
            lines.append(f"  from: {move.get('from')}")
            lines.append(f"  to: {move.get('to')}")
    else:
        lines.append("  none")
    return "\n".join(lines)
