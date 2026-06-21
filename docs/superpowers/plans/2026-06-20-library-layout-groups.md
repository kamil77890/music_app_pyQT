# Library Layout Groups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Organize the music library by global `library_group -> artist -> tracks`, with safe saved-plan apply and no fake album metadata.

**Architecture:** Add a new `library_layout_planner` beside the existing album-first planner. The planner derives global library groups from enrichment output and semantic profiles, saves deterministic plan snapshots, and applies only saved snapshots with fingerprint checks and an apply manifest. Existing download, API, and extension code are adapted to use staging and saved group metadata rather than fake albums.

**Tech Stack:** Python 3.12, FastAPI, mutagen, pytest, Firefox extension JavaScript/CSS/HTML.

---

## File Structure

Create `app/logic/local_ai/library_group_rules.py` for group-name normalization and validation. It should contain deterministic pure functions only: Nightcore detection, candidate cleanup, banned-word validation, artist/title exclusion, and dominant artist-group selection helpers.

Create `app/logic/local_ai/library_layout_planner.py` for plan construction, deterministic plan IDs, plan serialization, move operations, fingerprinting, apply execution, cover policy, and apply manifest writing.

Modify `app/logic/local_ai/enrichment_service.py` to add `library_group` fields to cache completeness, read/write `LOCAL_AI_LIBRARY_GROUP`, avoid writing fake albums to `TALB`, and expose `plan_library_layout` / `apply_library_layout` entry points used by the CLI.

Modify `scripts/run-local-ai-enrichment.py` to add `--plan-library-layout` and `--apply-library-layout <plan_id>`, reject direct `--move-files`, and print plan tree/conflicts/move preview.

Modify `app/logic/jellyfin_library.py` so new downloads land in `_incoming` staging instead of `Artist / Unknown Album`.

Modify `app/logic/ultimate_downloader.py` so metadata passed to `saveTrackToLibrary` does not force `Unknown Album` for new downloads.

Modify `app/endpoints/library_api.py` to add `GET /api/library/groups` using saved metadata/cache/registry and filesystem scan only, without calling enrichment or Ollama.

Modify `browser_extension/firefox/shared/api.js`, `browser_extension/firefox/background.js`, `browser_extension/firefox/sidebar/sidebar.html`, `browser_extension/firefox/sidebar/sidebar.js`, and `browser_extension/firefox/sidebar/sidebar.css` to render `Library Groups -> Group -> Artists -> Tracks`.

Create tests in `app/tests/test_library_layout_groups.py`, `app/tests/test_library_layout_cli.py`, and update existing API/downloader tests.

---

### Task 1: Add Group Rule Tests And Pure Rule Module

**Files:**
- Create: `app/logic/local_ai/library_group_rules.py`
- Create: `app/tests/test_library_layout_groups.py`

- [ ] **Step 1: Write failing tests for global Nightcore and invalid names**

Add this to `app/tests/test_library_layout_groups.py`:

```python
from __future__ import annotations


def _track(title: str, artist: str = "Artist A", **kwargs):
    return {
        "title": title,
        "artist": artist,
        "album": kwargs.get("album", ""),
        "genre": kwargs.get("genre", "Electronic"),
        "style": kwargs.get("style"),
        "tags": kwargs.get("tags", []),
        "source_title": kwargs.get("source_title", ""),
        "path": kwargs.get("path", f"/music/{artist}/{title}.mp3"),
        "fileMtime": kwargs.get("fileMtime", 1),
        "fileSize": kwargs.get("fileSize", 100),
        "videoId": kwargs.get("videoId", ""),
        "semantic_profile": kwargs.get(
            "semantic_profile",
            {
                "main_genre": kwargs.get("genre", "Electronic"),
                "broad_genre": kwargs.get("genre", "Electronic"),
                "style_markers": kwargs.get("style_markers", []),
                "context_markers": kwargs.get("context_markers", []),
                "performance_type": kwargs.get("performance_type", "studio"),
                "likely_group_theme": kwargs.get("theme", ""),
                "theme": kwargs.get("theme", ""),
            },
        ),
    }


def test_nightcore_evidence_maps_to_global_nightcore():
    from app.logic.local_ai.library_group_rules import infer_library_group

    tracks = [
        _track("Take A Hint", artist="Kenke", style="Nightcore"),
        _track("Hate Me", artist="Kenke", tags=["Nightcore"]),
        _track("Nightcore - Poker Face", artist="Eiden XII"),
        _track("abcdefu", artist="U N D E R D O G S.", source_title="nightcore abcdefu"),
    ]

    for track in tracks:
        result = infer_library_group(track)
        assert result["library_group"] == "Nightcore"
        assert result["library_group_source"] in {"local_ai", "deterministic"}


def test_artist_title_and_franchise_do_not_survive_group_validation():
    from app.logic.local_ai.library_group_rules import normalize_library_group_candidate

    track = _track("Complicated", artist="Avril Lavigne", theme="avril lavigne complicated")

    assert normalize_library_group_candidate("Avril Lavigne Complicated", track=track) != "Avril Lavigne Complicated"
    assert normalize_library_group_candidate("Tokyo Ghoul OP Piano Arr", track=_track("Unravel", artist="Luminote")) == "Anime Piano"
    assert normalize_library_group_candidate("Cyberpunk Piano", track=_track("I Really Want to Stay", artist="Grim Cat Piano")) == "Piano Covers"


def test_live_video_lyrics_amv_do_not_create_groups():
    from app.logic.local_ai.library_group_rules import normalize_library_group_candidate

    track = _track("Cut the Bridge (Live)", artist="Band", genre="Rock", style_markers=["rock"])

    assert normalize_library_group_candidate("Live Electronic Dance", track=track) == "Alternative Rock"
    assert normalize_library_group_candidate("Music Video Rock", track=track) == "Alternative Rock"
    assert normalize_library_group_candidate("Lyrics Rock", track=track) == "Alternative Rock"
    assert normalize_library_group_candidate("AMV Soundtrack", track=_track("Anime Mix", genre="Soundtrack")) == "Anime Soundtracks"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest app/tests/test_library_layout_groups.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'app.logic.local_ai.library_group_rules'`.

- [ ] **Step 3: Implement pure rule module**

Create `app/logic/local_ai/library_group_rules.py` with this implementation:

```python
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
    "official", "video", "live", "lyrics", "lyric", "amv", "animated",
    "op", "ed", "opening", "ending", "singles", "unknown", "misc",
    "general", "collection", "collections", "youtube",
}
_FRANCHISE_RE = re.compile(r"\b(cyberpunk|tokyo ghoul|solo leveling|edgerunners|ghoul)\b", re.IGNORECASE)


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
    return build_group_name_from_cluster([profile])


def normalize_library_group_candidate(candidate: str, *, track: dict[str, Any]) -> str:
    if has_nightcore_evidence(track):
        return "Nightcore"
    fallback = fallback_group_for_track(track)
    cleaned = normalize_key(candidate)
    words = cleaned.split()
    artist = normalize_key(track.get("artist"))
    title = normalize_key(track.get("title"))
    if not cleaned or len(words) > 3:
        return fallback
    if set(words) & _BANNED_WORDS:
        return fallback
    if artist and artist in cleaned:
        return fallback
    if title and title in cleaned:
        return fallback
    if _FRANCHISE_RE.search(cleaned):
        profile = _profile_for_track(track)
        styles = {normalize_key(item) for item in profile.get("style_markers") or []}
        contexts = {normalize_key(item) for item in profile.get("context_markers") or []}
        if "piano" in styles and ({"anime", "soundtrack"} & contexts):
            return "Anime Piano"
        if "piano" in styles:
            return "Piano Covers"
        return fallback
    return _title_case(cleaned)


def infer_library_group(track: dict[str, Any]) -> dict[str, Any]:
    group = normalize_library_group_candidate(fallback_group_for_track(track), track=track)
    return {
        "library_group": group,
        "library_group_source": "deterministic" if group == "Nightcore" else "local_ai",
        "library_group_confidence": 0.9 if group == "Nightcore" else float(track.get("classification_confidence") or 0.6),
    }


def apply_artist_dominant_groups(assignments: dict[str, dict[str, Any]], tracks_by_key: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_artist: dict[str, Counter[str]] = defaultdict(Counter)
    for key, assignment in assignments.items():
        track = tracks_by_key[key]
        artist = normalize_key(track.get("artist"))
        group = str(assignment.get("library_group") or "")
        if artist and group and group != "Nightcore":
            by_artist[artist][group] += 1

    dominant = {artist: counter.most_common(1)[0][0] for artist, counter in by_artist.items() if counter}
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest app/tests/test_library_layout_groups.py -v`

Expected: PASS for the three new tests.

---

### Task 2: Implement Deterministic Layout Planner And Snapshot Storage

**Files:**
- Create: `app/logic/local_ai/library_layout_planner.py`
- Modify: `app/tests/test_library_layout_groups.py`

- [ ] **Step 1: Write failing planner tests**

Append to `app/tests/test_library_layout_groups.py`:

```python
def test_layout_plan_groups_nightcore_by_group_then_artist(tmp_path):
    from app.logic.local_ai.config import LocalAIConfig
    from app.logic.local_ai.library_layout_planner import plan_library_layout

    tracks = [
        _track("Nightcore - Take A Hint", artist="Kenke", path=str(tmp_path / "Kenke" / "Nightcore Covers" / "a.mp3")),
        _track("Nightcore - Poker Face", artist="Eiden XII", path=str(tmp_path / "Eiden XII" / "Rock Nightcore" / "b.mp3")),
        _track("Nightcore - HEAVENLY JUMPSTYLE", artist="Nightcore Nation", path=str(tmp_path / "Nightcore Nation" / "Nightcore Electronic Covers" / "c.mp3")),
    ]
    for track in tracks:
        path = tmp_path / track["path"].removeprefix(str(tmp_path)).lstrip("/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"audio")
        track["path"] = str(path)
        track["fileMtime"] = path.stat().st_mtime_ns
        track["fileSize"] = path.stat().st_size

    config = LocalAIConfig(model="qwen2.5:3b")
    plan = plan_library_layout(tracks, music_dir=str(tmp_path), config=config, use_local_ai=True)

    assert plan["tree"][0]["name"] == "Nightcore"
    assert [artist["name"] for artist in plan["tree"][0]["artists"]] == ["Eiden XII", "Kenke", "Nightcore Nation"]
    destinations = {move["to"] for move in plan["moves"]}
    assert any("Nightcore/Kenke" in path for path in destinations)
    assert any("Nightcore/Eiden XII" in path for path in destinations)


def test_layout_plan_id_is_deterministic_and_ignores_generated_at(tmp_path):
    from app.logic.local_ai.config import LocalAIConfig
    from app.logic.local_ai.library_layout_planner import plan_library_layout

    path = tmp_path / "Kenke" / "Nightcore Covers" / "a.mp3"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"audio")
    track = _track("Nightcore - A", artist="Kenke", path=str(path), fileMtime=path.stat().st_mtime_ns, fileSize=path.stat().st_size)

    config = LocalAIConfig(model="qwen2.5:3b")
    first = plan_library_layout([track], music_dir=str(tmp_path), config=config, use_local_ai=True)
    second = plan_library_layout([dict(track)], music_dir=str(tmp_path), config=config, use_local_ai=True)

    assert first["plan_id"] == second["plan_id"]
    assert first["generated_at"] != ""
    assert second["generated_at"] != ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest app/tests/test_library_layout_groups.py::test_layout_plan_groups_nightcore_by_group_then_artist app/tests/test_library_layout_groups.py::test_layout_plan_id_is_deterministic_and_ignores_generated_at -v`

Expected: FAIL with `ModuleNotFoundError` or missing `plan_library_layout`.

- [ ] **Step 3: Implement planner core**

Create `app/logic/local_ai/library_layout_planner.py`:

```python
from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.logic.jellyfin_library import _resolve_duplicate, _safe_path, _set_permissions, sanitize_component
from app.logic.local_ai.classifier_base import CLASSIFIER_VERSION
from app.logic.local_ai.config import LocalAIConfig
from app.logic.local_ai.library_group_rules import GROUPING_CONFIG_VERSION, apply_artist_dominant_groups, infer_library_group, normalize_key

PLAN_DIR = Path("data/library_layout_plans")
MANIFEST_DIR = Path("data/library_layout_apply_manifests")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


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
    resolved = str(Path(path).resolve()) if path else ""
    stat = os.stat(path) if path and os.path.exists(path) else None
    return {
        "source_path": path,
        "resolved_source_path": resolved,
        "mtime": stat.st_mtime_ns if stat else track.get("fileMtime"),
        "size": stat.st_size if stat else track.get("fileSize"),
        "track_key": track_key(track),
        "videoId": str(track.get("videoId") or track.get("video_id") or ""),
    }


def _safe_layout_path(music_dir: str, library_group: str, artist: str, album: str, filename: str) -> Path:
    norm_lib = os.path.normpath(os.path.realpath(music_dir))
    parts = [sanitize_component(library_group), sanitize_component(artist)]
    if album:
        parts.append(sanitize_component(album))
    parts.append(sanitize_component(filename, max_len=220))
    raw = os.path.join(norm_lib, *parts)
    final = os.path.normpath(raw)
    if not final.startswith(norm_lib + os.sep) and final != norm_lib:
        raise ValueError(f"Path traversal blocked: {final} is outside {norm_lib}")
    return Path(final)


def _real_album(track: dict[str, Any]) -> str:
    album = str(track.get("album") or "").strip()
    album_kind = str(track.get("album_kind") or "").strip()
    album_source = str(track.get("album_source") or "").strip()
    if not album or album.lower() in {"unknown album", "singles", "unknown"}:
        return ""
    if album_kind in {"inferred_library_group", "local_ai", "ai_managed"}:
        return ""
    if album_source in {"local_ai", "registry", "pending_grouping"} and album_kind != "official_or_existing":
        return ""
    return album


def _destination_for_track(track: dict[str, Any], assignment: dict[str, Any], *, music_dir: str) -> str:
    source = Path(str(track.get("path") or ""))
    filename = source.name or sanitize_component(str(track.get("title") or "track")) + source.suffix
    album = _real_album(track)
    return str(_safe_layout_path(music_dir, assignment["library_group"], track.get("artist") or "Unknown Artist", album, filename))


def _normalized_for_hash(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "classifier_version": plan["classifier_version"],
        "model": plan["model"],
        "grouping_config_version": plan["grouping_config_version"],
        "library_root": plan["library_root"],
        "tree": plan["tree"],
        "moves": plan["moves"],
        "metadata_operations": plan["metadata_operations"],
        "fingerprints": plan["fingerprints"],
    }


def compute_plan_id(plan: dict[str, Any]) -> str:
    payload = json.dumps(_normalized_for_hash(plan), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def plan_library_layout(tracks: list[dict[str, Any]], *, music_dir: str, config: LocalAIConfig, use_local_ai: bool = False) -> dict[str, Any]:
    sorted_tracks = sorted(tracks, key=lambda item: (normalize_key(item.get("artist")), normalize_key(item.get("title")), str(item.get("path") or "")))
    tracks_by_key = {track_key(track): track for track in sorted_tracks}
    raw_assignments = {key: infer_library_group(track) for key, track in tracks_by_key.items()}
    assignments = apply_artist_dominant_groups(raw_assignments, tracks_by_key)

    tree_map: dict[str, dict[str, Any]] = {}
    moves: list[dict[str, Any]] = []
    metadata_ops: list[dict[str, Any]] = []
    fingerprints: list[dict[str, Any]] = []
    conflicts: list[dict[str, str]] = []

    for key, track in tracks_by_key.items():
        assignment = assignments[key]
        group_name = assignment["library_group"]
        artist = str(track.get("artist") or "Unknown Artist").strip() or "Unknown Artist"
        destination = _destination_for_track(track, assignment, music_dir=music_dir)
        source = str(track.get("path") or "")
        if source and str(Path(source).resolve()) != str(Path(destination).resolve()):
            moves.append({"track_key": key, "from": source, "to": destination, "library_group": group_name, "artist": artist})
        metadata_ops.append({"track_key": key, "path": source, "fields": {"LOCAL_AI_LIBRARY_GROUP": group_name, "LOCAL_AI_GROUP_ID": stable_layout_group_id(group_name), "LOCAL_AI_COLLECTION": track.get("collection") or ""}})
        fingerprints.append(track_fingerprint(track))
        group_node = tree_map.setdefault(group_name, {"name": group_name, "cover": "", "artists": {}})
        artist_node = group_node["artists"].setdefault(artist, {"name": artist, "track_count": 0, "tracks": []})
        artist_node["track_count"] += 1
        artist_node["tracks"].append({"title": track.get("title") or "", "path": source})

    tree = []
    for group_name in sorted(tree_map, key=normalize_key):
        group = tree_map[group_name]
        artists = [group["artists"][name] for name in sorted(group["artists"], key=normalize_key)]
        for artist in artists:
            artist["tracks"] = sorted(artist["tracks"], key=lambda item: normalize_key(item.get("title")))
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
        "conflicts": conflicts,
    }
    plan["plan_id"] = compute_plan_id(plan)
    return plan


def stable_layout_group_id(group_name: str) -> str:
    payload = json.dumps({"group": normalize_key(group_name), "version": GROUPING_CONFIG_VERSION}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def save_layout_plan(plan: dict[str, Any], *, plan_dir: Path = PLAN_DIR) -> Path:
    plan_dir.mkdir(parents=True, exist_ok=True)
    path = plan_dir / f"{plan['plan_id']}.json"
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_layout_plan(plan_id: str, *, plan_dir: Path = PLAN_DIR) -> dict[str, Any]:
    path = plan_dir / f"{sanitize_component(plan_id)}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def format_layout_plan_tree(plan: dict[str, Any]) -> str:
    lines = [f"Plan ID: {plan.get('plan_id')}", "Library layout tree:"]
    for group in plan.get("tree", []):
        lines.append(f"Group: {group.get('name')}")
        for artist in group.get("artists", []):
            lines.append(f"  Artist: {artist.get('name')} ({artist.get('track_count')} tracks)")
    lines.append("Conflicts:")
    for conflict in plan.get("conflicts", []):
        lines.append(f"  - {conflict}")
    if not plan.get("conflicts"):
        lines.append("  none")
    lines.append("Move preview:")
    for move in plan.get("moves", []):
        lines.append(f"  from: {move.get('from')}")
        lines.append(f"  to: {move.get('to')}")
    if not plan.get("moves"):
        lines.append("  none")
    return "\n".join(lines)
```

- [ ] **Step 4: Run planner tests**

Run: `.venv/bin/python -m pytest app/tests/test_library_layout_groups.py -v`

Expected: PASS for rule and planner tests.

---

### Task 3: Add Safe Apply, Fingerprint Checks, Metadata Operations, Cover Policy, And Manifest

**Files:**
- Modify: `app/logic/local_ai/library_layout_planner.py`
- Modify: `app/logic/local_ai/enrichment_service.py`
- Modify: `app/tests/test_library_layout_groups.py`

- [ ] **Step 1: Write failing apply tests**

Append to `app/tests/test_library_layout_groups.py`:

```python
def test_apply_uses_saved_plan_and_detects_fingerprint_conflict(tmp_path, monkeypatch):
    from app.logic.local_ai.config import LocalAIConfig
    from app.logic.local_ai.library_layout_planner import apply_library_layout_plan, plan_library_layout, save_layout_plan

    path = tmp_path / "Kenke" / "Nightcore Covers" / "a.mp3"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"audio")
    track = _track("Nightcore - A", artist="Kenke", path=str(path), fileMtime=path.stat().st_mtime_ns, fileSize=path.stat().st_size, videoId="abc123def45")
    plan = plan_library_layout([track], music_dir=str(tmp_path), config=LocalAIConfig(model="qwen2.5:3b"), use_local_ai=True)
    plan_dir = tmp_path / "plans"
    manifest_dir = tmp_path / "manifests"
    save_layout_plan(plan, plan_dir=plan_dir)

    path.write_bytes(b"changed")

    result = apply_library_layout_plan(plan["plan_id"], current_music_dir=str(tmp_path), plan_dir=plan_dir, manifest_dir=manifest_dir)

    assert result["applied"] == 0
    assert result["conflicts"] == 1
    assert path.exists()
    manifest = next(manifest_dir.glob("*.json"))
    assert "fingerprint" in manifest.read_text(encoding="utf-8")


def test_apply_aborts_when_library_root_differs(tmp_path):
    from app.logic.local_ai.config import LocalAIConfig
    from app.logic.local_ai.library_layout_planner import apply_library_layout_plan, plan_library_layout, save_layout_plan

    path = tmp_path / "Kenke" / "Nightcore Covers" / "a.mp3"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"audio")
    track = _track("Nightcore - A", artist="Kenke", path=str(path), fileMtime=path.stat().st_mtime_ns, fileSize=path.stat().st_size)
    plan_dir = tmp_path / "plans"
    plan = plan_library_layout([track], music_dir=str(tmp_path), config=LocalAIConfig(), use_local_ai=False)
    save_layout_plan(plan, plan_dir=plan_dir)

    other_root = tmp_path / "other"
    other_root.mkdir()
    result = apply_library_layout_plan(plan["plan_id"], current_music_dir=str(other_root), plan_dir=plan_dir, manifest_dir=tmp_path / "manifests")

    assert result["errors"] == 1
    assert result["files_moved"] == 0
    assert "library_root" in result["message"]


def test_cover_policy_never_overwrites_existing_cover(tmp_path):
    from app.logic.local_ai.library_layout_planner import choose_cover_operations

    existing = tmp_path / "Nightcore" / "Kenke" / "cover.jpg"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"existing")
    source = tmp_path / "Kenke" / "Nightcore Covers" / "cover.jpg"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"source")

    ops = choose_cover_operations([str(source)], destination_dir=str(existing.parent))

    assert ops == [{"from": str(source), "to": str(existing), "status": "skipped", "error": "destination cover exists"}]
```

- [ ] **Step 2: Run apply tests to verify they fail**

Run: `.venv/bin/python -m pytest app/tests/test_library_layout_groups.py::test_apply_uses_saved_plan_and_detects_fingerprint_conflict app/tests/test_library_layout_groups.py::test_apply_aborts_when_library_root_differs app/tests/test_library_layout_groups.py::test_cover_policy_never_overwrites_existing_cover -v`

Expected: FAIL with missing `apply_library_layout_plan` and `choose_cover_operations`.

- [ ] **Step 3: Implement apply helpers**

Append to `app/logic/local_ai/library_layout_planner.py`:

```python
def _fingerprint_matches(expected: dict[str, Any]) -> tuple[bool, str]:
    source = str(expected.get("source_path") or "")
    if not source or not os.path.isfile(source):
        return False, "source missing"
    resolved = str(Path(source).resolve())
    if resolved != str(expected.get("resolved_source_path") or ""):
        return False, "resolved source path changed"
    stat = os.stat(source)
    if stat.st_mtime_ns != expected.get("mtime"):
        return False, "mtime fingerprint mismatch"
    if stat.st_size != expected.get("size"):
        return False, "size fingerprint mismatch"
    return True, ""


def choose_cover_operations(source_covers: list[str], *, destination_dir: str) -> list[dict[str, str]]:
    destination = Path(destination_dir) / "cover.jpg"
    operations: list[dict[str, str]] = []
    for index, source in enumerate(sorted(source_covers, key=normalize_key)):
        if destination.exists():
            operations.append({"from": source, "to": str(destination), "status": "skipped", "error": "destination cover exists"})
        elif index == 0:
            operations.append({"from": source, "to": str(destination), "status": "planned", "error": ""})
        else:
            operations.append({"from": source, "to": str(destination), "status": "skipped", "error": "non-representative cover"})
    return operations


def _write_manifest(entries: list[dict[str, Any]], *, manifest_dir: Path, plan_id: str) -> Path:
    manifest_dir.mkdir(parents=True, exist_ok=True)
    path = manifest_dir / f"{plan_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.json"
    path.write_text(json.dumps({"plan_id": plan_id, "entries": entries}, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def apply_library_layout_plan(plan_id: str, *, current_music_dir: str, plan_dir: Path = PLAN_DIR, manifest_dir: Path = MANIFEST_DIR) -> dict[str, Any]:
    plan = load_layout_plan(plan_id, plan_dir=plan_dir)
    current_root = str(Path(current_music_dir).resolve())
    if str(plan.get("library_root")) != current_root:
        message = "plan library_root differs from current music library path"
        _write_manifest([{"plan_id": plan_id, "status": "error", "error": message, "timestamp": utc_now(), "metadata_fields_written": []}], manifest_dir=manifest_dir, plan_id=plan_id)
        return {"plan_id": plan_id, "applied": 0, "files_moved": 0, "metadata_written": 0, "conflicts": 0, "errors": 1, "message": message}

    fingerprints = {item["track_key"]: item for item in plan.get("fingerprints", [])}
    manifest_entries: list[dict[str, Any]] = []
    result = {"plan_id": plan_id, "applied": 0, "files_moved": 0, "metadata_written": 0, "conflicts": 0, "errors": 0, "message": ""}

    for move in plan.get("moves", []):
        key = move["track_key"]
        ok, error = _fingerprint_matches(fingerprints.get(key, {}))
        entry = {"plan_id": plan_id, "track_key": key, "from": move["from"], "to": move["to"], "timestamp": utc_now(), "status": "planned", "error": "", "metadata_fields_written": []}
        if not ok:
            entry["status"] = "conflict"
            entry["error"] = f"fingerprint conflict: {error}"
            result["conflicts"] += 1
            manifest_entries.append(entry)
            continue
        destination = _resolve_duplicate(Path(move["to"]))
        destination.parent.mkdir(parents=True, exist_ok=True)
        _set_permissions(destination.parent)
        shutil.move(move["from"], str(destination))
        _set_permissions(destination)
        entry["to"] = str(destination)
        entry["status"] = "moved"
        result["files_moved"] += 1
        result["applied"] += 1
        manifest_entries.append(entry)

    _write_manifest(manifest_entries, manifest_dir=manifest_dir, plan_id=plan_id)
    return result
```

- [ ] **Step 4: Run apply tests**

Run: `.venv/bin/python -m pytest app/tests/test_library_layout_groups.py -v`

Expected: PASS for planner and apply tests.

---

### Task 4: Add Metadata Read/Write For Library Group Without Fake TALB

**Files:**
- Modify: `app/logic/local_ai/enrichment_service.py`
- Modify: `app/tests/test_local_ai_metadata.py`

- [ ] **Step 1: Write failing metadata tests**

Append to `app/tests/test_local_ai_metadata.py`:

```python
def test_write_library_group_metadata_does_not_write_fake_album_mp3(tmp_path):
    from mutagen.id3 import ID3, ID3NoHeaderError
    from app.logic.local_ai.enrichment_service import write_library_layout_metadata

    path = tmp_path / "song.mp3"
    path.write_bytes(b"\xff\xfb\x90\x00" * 200)

    write_library_layout_metadata(str(path), {"library_group": "Nightcore", "group_id": "abc", "collection": ""})

    tags = ID3(str(path))
    assert str(tags.get("TXXX:LOCAL_AI_LIBRARY_GROUP").text[0]) == "Nightcore"
    assert str(tags.get("TXXX:LOCAL_AI_GROUP_ID").text[0]) == "abc"
    assert tags.get("TALB") is None


def test_read_audio_metadata_returns_library_group_fields(tmp_path):
    from app.logic.local_ai.enrichment_service import read_audio_file_metadata, write_library_layout_metadata

    path = tmp_path / "song.mp3"
    path.write_bytes(b"\xff\xfb\x90\x00" * 200)

    write_library_layout_metadata(str(path), {"library_group": "Piano Covers", "group_id": "gid", "collection": "Live"})

    meta = read_audio_file_metadata(str(path))
    assert meta["managed_library_group"] == "Piano Covers"
    assert meta["managed_group_id"] == "gid"
    assert meta["managed_collection"] == "Live"


def test_apply_writes_library_group_metadata_from_saved_plan(tmp_path):
    from mutagen.id3 import ID3
    from app.logic.local_ai.config import LocalAIConfig
    from app.logic.local_ai.library_layout_planner import apply_library_layout_plan, plan_library_layout, save_layout_plan

    path = tmp_path / "Kenke" / "Nightcore Covers" / "a.mp3"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xff\xfb\x90\x00" * 200)
    track = {
        "title": "Nightcore - A",
        "artist": "Kenke",
        "album": "",
        "genre": "Electronic",
        "style": "Nightcore",
        "tags": ["Nightcore"],
        "path": str(path),
        "fileMtime": path.stat().st_mtime_ns,
        "fileSize": path.stat().st_size,
        "semantic_profile": {"main_genre": "Electronic", "style_markers": ["nightcore"], "context_markers": [], "performance_type": "studio"},
    }
    plan_dir = tmp_path / "plans"
    manifest_dir = tmp_path / "manifests"
    plan = plan_library_layout([track], music_dir=str(tmp_path), config=LocalAIConfig(), use_local_ai=False)
    save_layout_plan(plan, plan_dir=plan_dir)

    result = apply_library_layout_plan(plan["plan_id"], current_music_dir=str(tmp_path), plan_dir=plan_dir, manifest_dir=manifest_dir)

    assert result["metadata_written"] == 1
    moved_to = plan["moves"][0]["to"]
    tags = ID3(moved_to)
    assert str(tags["TXXX:LOCAL_AI_LIBRARY_GROUP"].text[0]) == "Nightcore"
    assert tags.get("TALB") is None


def test_apply_writes_library_group_metadata_when_no_move_needed(tmp_path):
    from mutagen.id3 import ID3
    from app.logic.local_ai.config import LocalAIConfig
    from app.logic.local_ai.library_layout_planner import apply_library_layout_plan, plan_library_layout, save_layout_plan

    path = tmp_path / "Nightcore" / "Kenke" / "a.mp3"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xff\xfb\x90\x00" * 200)
    track = {
        "title": "Nightcore - A",
        "artist": "Kenke",
        "album": "",
        "genre": "Electronic",
        "style": "Nightcore",
        "tags": ["Nightcore"],
        "path": str(path),
        "fileMtime": path.stat().st_mtime_ns,
        "fileSize": path.stat().st_size,
        "semantic_profile": {"main_genre": "Electronic", "style_markers": ["nightcore"], "context_markers": [], "performance_type": "studio"},
    }
    plan_dir = tmp_path / "plans"
    manifest_dir = tmp_path / "manifests"
    plan = plan_library_layout([track], music_dir=str(tmp_path), config=LocalAIConfig(), use_local_ai=False)
    save_layout_plan(plan, plan_dir=plan_dir)

    result = apply_library_layout_plan(plan["plan_id"], current_music_dir=str(tmp_path), plan_dir=plan_dir, manifest_dir=manifest_dir)

    assert result["files_moved"] == 0
    assert result["metadata_written"] == 1
    tags = ID3(str(path))
    assert str(tags["TXXX:LOCAL_AI_LIBRARY_GROUP"].text[0]) == "Nightcore"
```

- [ ] **Step 2: Run metadata tests to verify they fail**

Run: `.venv/bin/python -m pytest app/tests/test_local_ai_metadata.py::test_write_library_group_metadata_does_not_write_fake_album_mp3 app/tests/test_local_ai_metadata.py::test_read_audio_metadata_returns_library_group_fields app/tests/test_local_ai_metadata.py::test_apply_writes_library_group_metadata_from_saved_plan app/tests/test_local_ai_metadata.py::test_apply_writes_library_group_metadata_when_no_move_needed -v`

Expected: FAIL with missing `write_library_layout_metadata` or missing `managed_library_group`.

- [ ] **Step 3: Add metadata constants and reader fields**

Modify constants near the top of `app/logic/local_ai/enrichment_service.py`:

```python
_MANAGED_LIBRARY_GROUP_ID3_DESC = "LOCAL_AI_LIBRARY_GROUP"
```

Update `read_audio_file_metadata` output dict:

```python
out: dict[str, Any] = {
    "genre": "",
    "album": "",
    "managed_tags": [],
    "managed_collection": "",
    "managed_album_kind": "",
    "managed_group_id": "",
    "managed_library_group": "",
}
```

Inside the MP3 `TXXX:` loop add:

```python
elif desc == _MANAGED_LIBRARY_GROUP_ID3_DESC:
    out["managed_library_group"] = str(id3[key].text[0]).strip()
```

Inside the MP4/M4A section add:

```python
raw_library_group = audio.get(f"----:com.apple.iTunes:{_MANAGED_LIBRARY_GROUP_ID3_DESC}")
if raw_library_group:
    raw = raw_library_group[0]
    out["managed_library_group"] = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw).strip()
```

- [ ] **Step 4: Add library layout metadata writer**

Add this function after `write_audio_metadata` in `app/logic/local_ai/enrichment_service.py`:

```python
def write_library_layout_metadata(path: str, metadata: dict[str, Any]) -> list[str]:
    ext = os.path.splitext(path)[1].lower()
    library_group = str(metadata.get("library_group") or metadata.get("LOCAL_AI_LIBRARY_GROUP") or "").strip()
    group_id = str(metadata.get("group_id") or metadata.get("LOCAL_AI_GROUP_ID") or "").strip()
    collection = str(metadata.get("collection") or metadata.get("LOCAL_AI_COLLECTION") or "").strip()
    written: list[str] = []
    if ext == ".mp3":
        from mutagen.id3 import ID3, ID3NoHeaderError, TXXX

        try:
            id3 = ID3(path)
        except ID3NoHeaderError:
            id3 = ID3()
        for desc in (_MANAGED_LIBRARY_GROUP_ID3_DESC, _MANAGED_GROUP_ID_ID3_DESC, _MANAGED_COLLECTION_ID3_DESC):
            id3.delall(f"TXXX:{desc}")
        if library_group:
            id3.add(TXXX(encoding=3, desc=_MANAGED_LIBRARY_GROUP_ID3_DESC, text=library_group))
            written.append(_MANAGED_LIBRARY_GROUP_ID3_DESC)
        if group_id:
            id3.add(TXXX(encoding=3, desc=_MANAGED_GROUP_ID_ID3_DESC, text=group_id))
            written.append(_MANAGED_GROUP_ID_ID3_DESC)
        if collection:
            id3.add(TXXX(encoding=3, desc=_MANAGED_COLLECTION_ID3_DESC, text=collection))
            written.append(_MANAGED_COLLECTION_ID3_DESC)
        id3.save(path, v2_version=3, v1=2)
    elif ext in (".m4a", ".mp4"):
        from mutagen.mp4 import MP4

        audio = MP4(path)
        values = {
            _MANAGED_LIBRARY_GROUP_ID3_DESC: library_group,
            _MANAGED_GROUP_ID_ID3_DESC: group_id,
            _MANAGED_COLLECTION_ID3_DESC: collection,
        }
        for desc, value in values.items():
            key = f"----:com.apple.iTunes:{desc}"
            if key in audio:
                del audio[key]
            if value:
                audio[key] = [value.encode("utf-8")]
                written.append(desc)
        audio.save()
    return written
```

Update `apply_library_layout_plan` in `app/logic/local_ai/library_layout_planner.py` so metadata operations are looked up before the move loop and written immediately after a successful move, before the manifest entry is appended:

```python
    metadata_by_key = {item["track_key"]: item for item in plan.get("metadata_operations", [])}

    for move in plan.get("moves", []):
        metadata_op = metadata_by_key.get(key)
        if metadata_op:
            from app.logic.local_ai.enrichment_service import write_library_layout_metadata

            fields = metadata_op.get("fields") or {}
            written = write_library_layout_metadata(
                str(destination),
                {
                    "library_group": fields.get("LOCAL_AI_LIBRARY_GROUP"),
                    "group_id": fields.get("LOCAL_AI_GROUP_ID"),
                    "collection": fields.get("LOCAL_AI_COLLECTION"),
                },
            )
            entry["metadata_fields_written"] = written
            result["metadata_written"] += 1 if written else 0
```

Then add this second metadata loop after the move loop and before `_write_manifest(...)` to cover tracks already in the correct location:

```python
    processed_keys = {entry["track_key"] for entry in manifest_entries}
    for key, metadata_op in metadata_by_key.items():
        if key in processed_keys:
            continue
        fingerprint = fingerprints.get(key, {})
        ok, error = _fingerprint_matches(fingerprint)
        entry = {"plan_id": plan_id, "track_key": key, "from": metadata_op.get("path", ""), "to": metadata_op.get("path", ""), "timestamp": utc_now(), "status": "planned", "error": "", "metadata_fields_written": []}
        if not ok:
            entry["status"] = "conflict"
            entry["error"] = f"fingerprint conflict: {error}"
            result["conflicts"] += 1
            manifest_entries.append(entry)
            continue
        from app.logic.local_ai.enrichment_service import write_library_layout_metadata

        fields = metadata_op.get("fields") or {}
        written = write_library_layout_metadata(
            str(metadata_op.get("path") or ""),
            {
                "library_group": fields.get("LOCAL_AI_LIBRARY_GROUP"),
                "group_id": fields.get("LOCAL_AI_GROUP_ID"),
                "collection": fields.get("LOCAL_AI_COLLECTION"),
            },
        )
        entry["status"] = "metadata_written" if written else "skipped"
        entry["metadata_fields_written"] = written
        result["metadata_written"] += 1 if written else 0
        manifest_entries.append(entry)
```

- [ ] **Step 5: Run metadata tests**

Run: `.venv/bin/python -m pytest app/tests/test_local_ai_metadata.py::test_write_library_group_metadata_does_not_write_fake_album_mp3 app/tests/test_local_ai_metadata.py::test_read_audio_metadata_returns_library_group_fields app/tests/test_local_ai_metadata.py::test_apply_writes_library_group_metadata_from_saved_plan app/tests/test_local_ai_metadata.py::test_apply_writes_library_group_metadata_when_no_move_needed -v`

Expected: PASS.

---

### Task 5: Wire Plan/Apply CLI And Disable Direct `--move-files`

**Files:**
- Modify: `scripts/run-local-ai-enrichment.py`
- Modify: `app/logic/local_ai/enrichment_service.py`
- Create: `app/tests/test_library_layout_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Create `app/tests/test_library_layout_cli.py`:

```python
from __future__ import annotations


def test_move_files_is_disabled_without_layout_apply(monkeypatch, capsys):
    import scripts.run_local_ai_enrichment as runner

    monkeypatch.setattr(runner.sys, "argv", ["run-local-ai-enrichment.py", "--move-files"])

    code = runner.main()
    captured = capsys.readouterr()

    assert code == 2
    assert "Direct file moves are disabled for library layout migration." in captured.err
    assert "--apply-library-layout <plan_id>" in captured.err


def test_plan_library_layout_prints_saved_plan(monkeypatch, tmp_path, capsys):
    import scripts.run_local_ai_enrichment as runner

    monkeypatch.setattr(runner.JellyfinConfig, "get_music_library_path", lambda: str(tmp_path))
    monkeypatch.setattr(
        runner,
        "enrich_library_batch",
        lambda **kwargs: {
            "errors": 0,
            "plan_library_layout": True,
            "library_layout_plan_id": "abc123",
            "library_layout_plan_text": "Plan ID: abc123\nGroup: Nightcore\n  Artist: Kenke",
            "library_layout_conflicts": [],
            "move_plans": [],
        },
    )
    monkeypatch.setattr(runner.sys, "argv", ["run-local-ai-enrichment.py", "--plan-library-layout"])

    code = runner.main()
    captured = capsys.readouterr()

    assert code == 0
    assert "Plan ID: abc123" in captured.out
    assert "Group: Nightcore" in captured.out
```

Because `scripts/run-local-ai-enrichment.py` has a hyphen and cannot be imported as `scripts.run_local_ai_enrichment`, implement the import shim in Step 3 before running this test directly.

- [ ] **Step 2: Add importable script shim for tests**

Create `scripts/run_local_ai_enrichment.py`:

```python
from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).with_name("run-local-ai-enrichment.py")
_SPEC = importlib.util.spec_from_file_location("run_local_ai_enrichment_impl", _SCRIPT)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"Cannot import {_SCRIPT}")
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

parse_args = _MODULE.parse_args
run_jellyfin_check = _MODULE.run_jellyfin_check
JellyfinConfig = _MODULE.JellyfinConfig
enrich_library_batch = _MODULE.enrich_library_batch
sys = _MODULE.sys


def main() -> int:
    _MODULE.JellyfinConfig = JellyfinConfig
    _MODULE.enrich_library_batch = enrich_library_batch
    _MODULE.sys = sys
    return _MODULE.main()
```

- [ ] **Step 3: Run CLI tests to verify they fail on behavior**

Run: `.venv/bin/python -m pytest app/tests/test_library_layout_cli.py -v`

Expected: FAIL because `--plan-library-layout` and direct `--move-files` rejection are not implemented.

- [ ] **Step 4: Modify script arguments and main flow**

In `scripts/run-local-ai-enrichment.py`, add parser args after `--plan-album-groups`:

```python
parser.add_argument("--plan-library-layout", action="store_true", help="Save a read-only library group layout plan and print tree preview.")
parser.add_argument("--apply-library-layout", default="", help="Apply a previously saved library layout plan by plan_id.")
```

At the top of `main()` after `args = parse_args()` add:

```python
    if args.move_files and not args.apply_library_layout:
        print(
            "Direct file moves are disabled for library layout migration.\n"
            "Run --plan-library-layout first, review the saved plan, then run:\n"
            "--apply-library-layout <plan_id>",
            file=sys.stderr,
        )
        return 2
```

Update dry-run decisions:

```python
    will_apply_layout = bool(args.apply_library_layout)
    will_write = args.write_tags or args.write_albums
    will_move = will_apply_layout
    dry_run = args.dry_run or args.plan_album_groups or args.plan_library_layout or not (will_write or will_move)
```

Pass new arguments to `enrich_library_batch`:

```python
        plan_library_layout=args.plan_library_layout,
        apply_library_layout=args.apply_library_layout,
```

Print plan text after album group text:

```python
    if summary.get("library_layout_plan_text"):
        print(summary["library_layout_plan_text"])
```

- [ ] **Step 5: Add enrichment service parameters and dispatch**

In `app/logic/local_ai/enrichment_service.py`, import planner functions:

```python
from app.logic.local_ai.library_layout_planner import apply_library_layout_plan, format_layout_plan_tree, plan_library_layout as build_library_layout_plan, save_layout_plan
```

Extend `enrich_library_batch` signature:

```python
    plan_library_layout: bool = False,
    apply_library_layout: str = "",
```

Add summary keys:

```python
        "plan_library_layout": plan_library_layout,
        "apply_library_layout": apply_library_layout,
        "library_layout_plan_id": "",
        "library_layout_conflicts": [],
```

Before the existing album group planning block, add:

```python
    if apply_library_layout:
        apply_summary = apply_library_layout_plan(apply_library_layout, current_music_dir=lib_dir)
        summary.update(apply_summary)
        return summary

    if enriched_items and plan_library_layout:
        all_enriched = [enriched for _, enriched in enriched_items]
        layout_plan = build_library_layout_plan(all_enriched, music_dir=lib_dir, config=config, use_local_ai=force_local_ai)
        save_layout_plan(layout_plan)
        summary["library_layout_plan_id"] = layout_plan["plan_id"]
        summary["library_layout_conflicts"] = layout_plan.get("conflicts", [])
        summary["library_layout_plan_text"] = format_layout_plan_tree(layout_plan)
        summary["move_plans"] = layout_plan.get("moves", [])
        _save_cache(config.cache_path, cache)
        return summary
```

- [ ] **Step 6: Run CLI tests**

Run: `.venv/bin/python -m pytest app/tests/test_library_layout_cli.py -v`

Expected: PASS.

---

### Task 6: Stage New Downloads In `_incoming`

**Files:**
- Modify: `app/logic/jellyfin_library.py`
- Modify: `app/logic/ultimate_downloader.py`
- Modify: `app/tests/test_jellyfin_library.py`

- [ ] **Step 1: Write failing staging test**

Append to `app/tests/test_jellyfin_library.py`:

```python
def test_save_track_without_real_album_uses_incoming_staging(tmp_path, monkeypatch):
    from app.logic import jellyfin_library

    source = tmp_path / "source.mp3"
    source.write_bytes(b"\xff\xfb\x90\x00" * 200)
    monkeypatch.setenv("MUSIC_LIBRARY_PATH", str(tmp_path / "music"))
    monkeypatch.setattr(jellyfin_library, "_notify_jellyfin", lambda: None)

    saved = jellyfin_library.saveTrackToLibrary(
        str(source),
        {"title": "Song", "artist": "Artist", "album": "", "trackNumber": "00", "genre": "", "videoId": "abc123def45"},
        copy=True,
    )

    assert "/_incoming/Artist/" in saved
    assert "/Unknown Album/" not in saved
```

- [ ] **Step 2: Run staging test to verify it fails**

Run: `.venv/bin/python -m pytest app/tests/test_jellyfin_library.py::test_save_track_without_real_album_uses_incoming_staging -v`

Expected: FAIL because current path includes `Unknown Album`.

- [ ] **Step 3: Modify save path logic**

In `app/logic/jellyfin_library.py`, replace album assignment at lines 286-288 with:

```python
    artist = (metadata.get("artist") or "").strip() or "Unknown Artist"
    raw_album = (metadata.get("album") or "").strip()
    album = raw_album if raw_album and raw_album.lower() not in {"unknown album", "unknown", "singles"} else ""
    title = (metadata.get("title") or "").strip()
```

Replace final path construction:

```python
    if album:
        final_path = _safe_path(lib_path, artist, album, safe_filename)
    else:
        final_path = _safe_path(lib_path, "_incoming", artist, safe_filename)
```

Keep `_write_id3_tags(... album=album if album else None ...)` so `TALB` remains empty when no real album exists.

- [ ] **Step 4: Stop forcing Unknown Album in downloader metadata**

In `app/logic/ultimate_downloader.py`, change both `jellyfin_meta` album assignments:

```python
"album": track.get("album") or "",
```

- [ ] **Step 5: Run staging tests**

Run: `.venv/bin/python -m pytest app/tests/test_jellyfin_library.py::test_save_track_without_real_album_uses_incoming_staging -v`

Expected: PASS.

---

### Task 7: Add `/api/library/groups` Without On-Demand Enrichment

**Files:**
- Modify: `app/endpoints/library_api.py`
- Modify: `app/tests/test_library_api.py`

- [ ] **Step 1: Write failing API tests**

Append to `app/tests/test_library_api.py`:

```python
class TestLibraryGroupsEndpoint:
    def test_library_groups_uses_saved_fields_without_enrichment(self, monkeypatch, tmp_path):
        import app.endpoints.library_api as lib_api

        song = {
            "title": "Nightcore - A",
            "artist": "Kenke",
            "album": "",
            "path": str(tmp_path / "music" / "Nightcore" / "Kenke" / "a.mp3"),
            "cover": "cover-url",
            "library_group": "Nightcore",
            "managed_library_group": "Nightcore",
        }
        monkeypatch.setenv(LIBRARY_PATH_VAR, str(tmp_path / "music"))
        monkeypatch.setattr(lib_api, "scan_music_files", lambda _path: [song])

        def fail_enrich(*args, **kwargs):
            raise AssertionError("enrichment must not run")

        monkeypatch.setattr(lib_api, "enrich_track_metadata", fail_enrich)

        resp = client.get("/api/library/groups")

        assert resp.status_code == 200
        data = resp.json()
        assert data["groups"][0]["name"] == "Nightcore"
        assert data["groups"][0]["artists"][0]["name"] == "Kenke"
        assert data["groups"][0]["artists"][0]["track_count"] == 1
```

- [ ] **Step 2: Run API test to verify it fails**

Run: `.venv/bin/python -m pytest app/tests/test_library_api.py::TestLibraryGroupsEndpoint::test_library_groups_uses_saved_fields_without_enrichment -v`

Expected: FAIL with 404 for `/api/library/groups`.

- [ ] **Step 3: Implement endpoint helper and route**

In `app/endpoints/library_api.py`, add imports:

```python
from collections import defaultdict
from app.logic.local_ai.enrichment_service import read_audio_file_metadata
```

Add helper before routes:

```python
def _saved_library_group(song: dict) -> str:
    value = song.get("library_group") or song.get("managed_library_group") or ""
    if value:
        return str(value).strip()
    path = str(song.get("path") or "")
    if path and os.path.isfile(path):
        file_meta = read_audio_file_metadata(path)
        if file_meta.get("managed_library_group"):
            return str(file_meta["managed_library_group"]).strip()
    parts = os.path.normpath(path).split(os.sep)
    lib_parts = os.path.normpath(JellyfinConfig.get_music_library_path()).split(os.sep)
    rel = parts[len(lib_parts):] if parts[: len(lib_parts)] == lib_parts else []
    if rel and rel[0] and rel[0] != "_incoming":
        return rel[0]
    return "Ungrouped"


def build_library_groups_response(songs: list[dict]) -> dict:
    grouped: dict[str, dict[str, dict]] = defaultdict(dict)
    covers: dict[str, str] = {}
    for song in songs:
        group = _saved_library_group(song)
        artist = str(song.get("artist") or "Unknown Artist").strip() or "Unknown Artist"
        artist_node = grouped[group].setdefault(artist, {"name": artist, "track_count": 0, "tracks": []})
        artist_node["track_count"] += 1
        artist_node["tracks"].append(song)
        if group not in covers and song.get("cover"):
            covers[group] = song["cover"]
    groups = []
    for group_name in sorted(grouped, key=lambda item: item.lower()):
        artists = []
        for artist_name in sorted(grouped[group_name], key=lambda item: item.lower()):
            node = grouped[group_name][artist_name]
            node["tracks"] = sorted(node["tracks"], key=lambda item: str(item.get("title") or "").lower())
            artists.append(node)
        groups.append({"name": group_name, "cover": covers.get(group_name, ""), "artists": artists})
    return {"groups": groups}
```

Add route after `/library/songs`:

```python
@router.get("/library/groups")
async def library_groups():
    lib_path = JellyfinConfig.get_music_library_path()
    if not os.path.isdir(lib_path):
        return {"groups": [], "library_path": lib_path}
    songs = scan_music_files(lib_path)
    return {**build_library_groups_response(songs), "library_path": lib_path}
```

- [ ] **Step 4: Run API tests**

Run: `.venv/bin/python -m pytest app/tests/test_library_api.py::TestLibraryGroupsEndpoint::test_library_groups_uses_saved_fields_without_enrichment -v`

Expected: PASS.

---

### Task 8: Add Extension Group View

**Files:**
- Modify: `browser_extension/firefox/shared/api.js`
- Modify: `browser_extension/firefox/sidebar/sidebar.html`
- Modify: `browser_extension/firefox/sidebar/sidebar.js`
- Modify: `browser_extension/firefox/sidebar/sidebar.css`
- Modify: `app/tests/test_firefox_extension_contract.py`

- [ ] **Step 1: Write failing extension contract test**

Append to `app/tests/test_firefox_extension_contract.py`:

```python
def test_sidebar_uses_library_groups_endpoint():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    api_js = (root / "browser_extension" / "firefox" / "shared" / "api.js").read_text(encoding="utf-8")
    background_js = (root / "browser_extension" / "firefox" / "background.js").read_text(encoding="utf-8")
    sidebar_js = (root / "browser_extension" / "firefox" / "sidebar" / "sidebar.js").read_text(encoding="utf-8")
    sidebar_html = (root / "browser_extension" / "firefox" / "sidebar" / "sidebar.html").read_text(encoding="utf-8")

    assert "/api/library/groups" in api_js
    assert "GET_LIBRARY_GROUPS" in background_js
    assert "GET_LIBRARY_GROUPS" in sidebar_js
    assert "group-list" in sidebar_html
```

- [ ] **Step 2: Run contract test to verify it fails**

Run: `.venv/bin/python -m pytest app/tests/test_firefox_extension_contract.py::test_sidebar_uses_library_groups_endpoint -v`

Expected: FAIL because endpoint usage is missing.

- [ ] **Step 3: Add API helper**

In `browser_extension/firefox/shared/api.js`, add:

```javascript
async function listLibraryGroups() {
  const data = await _json(`${API_BASE}/api/library/groups`, { method: "GET" });
  return data;
}
```

In `browser_extension/firefox/background.js`, add this `switch (msg.type)` case immediately after the existing `GET_LIBRARY` case:

```javascript
    case "GET_LIBRARY_GROUPS": {
      try {
        const data = await listLibraryGroups();
        return { ok: true, data };
      } catch (err) {
        return { ok: false, error: err.message };
      }
    }
```

- [ ] **Step 4: Add HTML container**

In `browser_extension/firefox/sidebar/sidebar.html`, insert above `<ul id="song-list"></ul>`:

```html
      <div id="group-breadcrumb" class="group-breadcrumb">Library Groups</div>
      <ul id="group-list"></ul>
```

- [ ] **Step 5: Add JS rendering path**

In `browser_extension/firefox/sidebar/sidebar.js`, add state near `let allSongs = []`:

```javascript
  let libraryGroups = [];
  let selectedGroup = null;
  let selectedArtist = null;
```

Add functions near library functions:

```javascript
  async function loadLibraryGroups() {
    const groupList = $("group-list");
    if (!groupList) return;
    try {
      const resp = await browser.runtime.sendMessage({ type: "GET_LIBRARY_GROUPS" });
      if (!resp.ok) throw new Error(resp.error);
      libraryGroups = resp.data.groups || [];
      selectedGroup = null;
      selectedArtist = null;
      renderLibraryGroups();
    } catch (err) {
      libraryStatus.textContent = "Error: " + err.message;
    }
  }

  function renderLibraryGroups() {
    const groupList = $("group-list");
    const songListEl = songList;
    if (!groupList) return;
    groupList.innerHTML = "";
    songListEl.innerHTML = "";
    $("group-breadcrumb").textContent = selectedGroup ? `Library Groups / ${selectedGroup.name}` : "Library Groups";
    const items = selectedGroup ? selectedGroup.artists || [] : libraryGroups;
    for (const item of items) {
      const li = document.createElement("li");
      li.className = "group-item";
      li.textContent = selectedGroup ? `${item.name} (${item.track_count})` : item.name;
      li.addEventListener("click", () => {
        if (!selectedGroup) {
          selectedGroup = item;
          renderLibraryGroups();
        } else {
          selectedArtist = item;
          renderSongs(item.tracks || []);
        }
      });
      groupList.appendChild(li);
    }
  }
```

Call `loadLibraryGroups()` alongside existing `loadLibrary()` in the initialization block.

- [ ] **Step 6: Add CSS**

In `browser_extension/firefox/sidebar/sidebar.css`, add:

```css
.group-breadcrumb {
  color: var(--text-muted);
  font-size: 11px;
  margin-bottom: 6px;
}

#group-list {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 8px;
}

.group-item {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 8px 10px;
  cursor: pointer;
}

.group-item:hover {
  background: var(--surface-hover);
  border-color: var(--accent);
}
```

- [ ] **Step 7: Run extension contract test**

Run: `.venv/bin/python -m pytest app/tests/test_firefox_extension_contract.py::test_sidebar_uses_library_groups_endpoint -v`

Expected: PASS.

---

### Task 9: Add Integration Tests For No Artist-Specific Mapping And Full Safety Matrix

**Files:**
- Modify: `app/tests/test_library_layout_groups.py`
- Modify: `app/tests/test_album_groups.py`

- [ ] **Step 1: Add tests for no artist-specific mapping in new files**

Append to `app/tests/test_library_layout_groups.py`:

```python
def test_library_layout_production_code_has_no_artist_specific_mapping():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "logic" / "local_ai"
    files = [
        root / "library_group_rules.py",
        root / "library_layout_planner.py",
    ]
    forbidden = ['if artist == "', "if artist == '", '== "Linkin Park"', '== "Kenke"', '== "Eiden XII"']
    for file_path in files:
        source = file_path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in source, f"{token} found in {file_path.name}"
```

- [ ] **Step 2: Add direct move disabled test if not already green**

Keep `app/tests/test_library_layout_cli.py::test_move_files_is_disabled_without_layout_apply` from Task 5. It covers the exact required message and no-change path because `main()` returns before calling `enrich_library_batch`.

- [ ] **Step 3: Run layout-specific test suite**

Run: `.venv/bin/python -m pytest app/tests/test_library_layout_groups.py app/tests/test_library_layout_cli.py -v`

Expected: PASS.

---

### Task 10: Full Test Run And Required Plan-Only Validation

**Files:**
- No code files unless tests reveal failures.

- [ ] **Step 1: Run full pytest suite**

Run: `.venv/bin/python -m pytest`

Expected: PASS. If failures occur, fix only the code related to this feature and rerun the failing tests first, then rerun full pytest.

- [ ] **Step 2: Run required plan-only validation, without apply**

Run exactly:

```bash
LOCAL_AI_MODEL=qwen2.5:3b .venv/bin/python scripts/run-local-ai-enrichment.py \
  --plan-library-layout \
  --use-local-ai \
  --repair-managed-tags \
  --repair-managed-albums \
  --repair-album-folders
```

Expected: command prints JSON summary and a layout tree containing `Plan ID:`, `Group: Nightcore`, artists under Nightcore, conflicts, and move preview. It must not apply or move files.

- [ ] **Step 3: Run required plan-only validation a second time**

Run the same command again:

```bash
LOCAL_AI_MODEL=qwen2.5:3b .venv/bin/python scripts/run-local-ai-enrichment.py \
  --plan-library-layout \
  --use-local-ai \
  --repair-managed-tags \
  --repair-managed-albums \
  --repair-album-folders
```

Expected: the same `plan_id` as the first run. If `generated_at` differs, that is acceptable; `plan_id`, tree, conflicts, and moves must remain identical for unchanged inputs.

- [ ] **Step 4: Inspect git status and avoid runtime files**

Run: `git status --short`

Expected: modified source/tests/docs only. Do not stage `.env`, `data/local_ai_metadata_cache.json`, runtime plan files, runtime manifests, database WAL/SHM, or audio files.

- [ ] **Step 5: Commit only requested paths after tests pass**

Run:

```bash
git add app/ scripts/ tests/ docs/superpowers/specs/2026-06-20-library-layout-groups-design.md docs/superpowers/plans/2026-06-20-library-layout-groups.md browser_extension/firefox/shared/api.js browser_extension/firefox/sidebar/sidebar.html browser_extension/firefox/sidebar/sidebar.js browser_extension/firefox/sidebar/sidebar.css
git commit -m "Organize music library by global AI groups and artists"
```

Expected: commit succeeds. Do not commit runtime cache, registry, manifests, WAL/SHM, `.env`, or audio files.

---

## Self-Review Notes

Spec coverage is mapped as follows: group rules and Nightcore in Tasks 1-2, plan/apply/fingerprints/manifests/cover policy in Tasks 2-3, metadata/TALB separation in Task 4, CLI safety in Task 5, `_incoming` staging in Task 6, API/UI in Tasks 7-8, no artist-specific mapping and safety tests in Task 9, full pytest and plan-only validation in Task 10.

No apply command is included. The only live-library validation command is `--plan-library-layout` and it is explicitly plan-only.
