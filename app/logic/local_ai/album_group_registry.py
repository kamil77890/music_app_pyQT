from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.logic.local_ai.classifier_base import CLASSIFIER_VERSION


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _normalize_key(value: Any) -> str:
    return str(value or "").strip().lower()


def stable_group_id(*, artist_scope: str, group_name: str, member_track_keys: list[str]) -> str:
    payload = {
        "artist_scope": _normalize_key(artist_scope),
        "group_name": _normalize_key(group_name),
        "member_track_keys": sorted(member_track_keys),
        "classifier_version": CLASSIFIER_VERSION,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return digest[:16]


def load_registry(path: str) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.is_file():
        return {"classifier_version": CLASSIFIER_VERSION, "groups": {}, "track_assignments": {}}
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        return {"classifier_version": CLASSIFIER_VERSION, "groups": {}, "track_assignments": {}}
    if not isinstance(data, dict):
        return {"classifier_version": CLASSIFIER_VERSION, "groups": {}, "track_assignments": {}}
    data.setdefault("groups", {})
    data.setdefault("track_assignments", {})
    return data


def save_registry(path: str, registry: dict[str, Any], *, model: str = "") -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "classifier_version": CLASSIFIER_VERSION,
        "model": model,
        "updated_at": _utc_now(),
        "groups": registry.get("groups", {}),
        "track_assignments": registry.get("track_assignments", {}),
    }
    file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def registry_group_for_track(registry: dict[str, Any], track_key: str) -> dict[str, Any] | None:
    group_id = registry.get("track_assignments", {}).get(track_key)
    if not group_id:
        return None
    group = registry.get("groups", {}).get(group_id)
    return group if isinstance(group, dict) else None


def upsert_group(
    registry: dict[str, Any],
    *,
    group_id: str,
    group_name: str,
    artist_scope: str,
    semantic_fingerprint: str,
    member_track_keys: list[str],
    member_paths: list[str],
    model: str,
) -> None:
    now = _utc_now()
    existing = registry.setdefault("groups", {}).get(group_id, {})
    registry["groups"][group_id] = {
        "group_id": group_id,
        "group_name": group_name,
        "artist_scope": artist_scope,
        "semantic_fingerprint": semantic_fingerprint,
        "member_track_keys": sorted(member_track_keys),
        "member_paths": sorted(member_paths),
        "model": model,
        "classifier_version": CLASSIFIER_VERSION,
        "created_at": existing.get("created_at") or now,
        "updated_at": now,
    }
    for track_key in member_track_keys:
        registry.setdefault("track_assignments", {})[track_key] = group_id
