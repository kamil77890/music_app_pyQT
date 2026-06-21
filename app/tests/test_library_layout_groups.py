from __future__ import annotations

import json
from pathlib import Path

import struct

import pytest


def _make_minimal_mp4(path):
    def _atom(name, data):
        return struct.pack(">I", 8 + len(data)) + name + data

    ftyp = _atom(b"ftyp", b"M4A \x00\x00\x02\x00M4A \x00\x00\x00\x00mp42\x00\x00\x00\x00")
    mvhd = _atom(
        b"mvhd",
        b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02"
        b"\x00\x00\x00\x00\x01\x00\x00\x00\x01\x00\x00\x00"
        b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00"
        b"\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x01\x00"
        b"\x00\x00\x00\x01\x00\x00\x00\x00\x00@\x00\x00\x00"
        b"\x00\x00\x00\x00\x00\x00\x00\x02",
    )
    moov = _atom(b"moov", mvhd)
    mdat = _atom(b"mdat", b"\x00" * 100)
    path.write_bytes(ftyp + moov + mdat)


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
    assert (
        normalize_library_group_candidate(
            "Tokyo Ghoul OP Piano Arr",
            track=_track("Unravel OP", artist="Luminote", style_markers=["piano"], context_markers=["anime"]),
        )
        == "Anime Piano"
    )
    assert (
        normalize_library_group_candidate(
            "Cyberpunk Piano", track=_track("I Really Want to Stay", artist="Grim Cat Piano", style_markers=["piano"])
        )
        == "Piano Covers"
    )


def test_live_video_lyrics_amv_do_not_create_groups():
    from app.logic.local_ai.library_group_rules import normalize_library_group_candidate

    track = _track("Cut the Bridge (Live)", artist="Band", genre="Rock", style_markers=["rock"])

    assert normalize_library_group_candidate("Live Electronic Dance", track=track) == "Alternative Rock"
    assert normalize_library_group_candidate("Music Video Rock", track=track) == "Alternative Rock"
    assert normalize_library_group_candidate("Lyrics Rock", track=track) == "Alternative Rock"
    assert normalize_library_group_candidate("AMV Soundtrack", track=_track("Anime Mix", genre="Soundtrack")) == "Anime Soundtracks"


def test_arbitrary_short_group_candidates_fall_back_to_deterministic_groups():
    from app.logic.local_ai.library_group_rules import normalize_library_group_candidate

    electronic_track = _track("Late Night Drive", genre="Electronic", style_markers=["electronic"])
    rock_track = _track("Bridge", genre="Rock", style_markers=["rock"])

    assert normalize_library_group_candidate("Dream Mix", track=electronic_track) == "Electronic"
    assert normalize_library_group_candidate("Foo Bar", track=rock_track) == "Alternative Rock"


def test_recognized_candidate_labels_need_track_evidence():
    from app.logic.local_ai.library_group_rules import normalize_library_group_candidate

    track = _track("Late Night Drive", genre="Electronic", style_markers=["electronic"])

    assert normalize_library_group_candidate("Piano Covers", track=track) == "Electronic"
    assert normalize_library_group_candidate("Anime Mix", track=track) == "Electronic"
    assert normalize_library_group_candidate("Anime Piano", track=track) == "Electronic"


def test_artist_dominant_group_merge_requires_strict_majority():
    from app.logic.local_ai.library_group_rules import apply_artist_dominant_groups

    tracks_by_key = {
        "a": _track("Track A", artist="Artist A"),
        "b": _track("Track B", artist="Artist A"),
        "c": _track("Track C", artist="Artist A"),
    }
    assignments = {
        "a": {"library_group": "Alternative Rock"},
        "b": {"library_group": "Piano Covers"},
        "c": {"library_group": "Music Video Rock"},
    }

    result = apply_artist_dominant_groups(assignments, tracks_by_key)

    assert result["c"]["library_group"] == "Music Video Rock"


def test_layout_plan_groups_nightcore_by_group_then_artist(tmp_path):
    from app.logic.local_ai.config import LocalAIConfig
    from app.logic.local_ai.library_layout_planner import plan_library_layout

    tracks = [
        _track("Nightcore - Take A Hint", artist="Kenke", path=str(tmp_path / "Kenke" / "Nightcore Covers" / "a.mp3")),
        _track("Nightcore - Poker Face", artist="Eiden XII", path=str(tmp_path / "Eiden XII" / "Rock Nightcore" / "b.mp3")),
        _track(
            "Nightcore - HEAVENLY JUMPSTYLE",
            artist="Nightcore Nation",
            path=str(tmp_path / "Nightcore Nation" / "Nightcore Electronic Covers" / "c.mp3"),
        ),
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
    track = _track(
        "Nightcore - A",
        artist="Kenke",
        path=str(path),
        fileMtime=path.stat().st_mtime_ns,
        fileSize=path.stat().st_size,
    )

    config = LocalAIConfig(model="qwen2.5:3b")
    first = plan_library_layout([track], music_dir=str(tmp_path), config=config, use_local_ai=True)
    second = plan_library_layout([dict(track)], music_dir=str(tmp_path), config=config, use_local_ai=True)

    assert first["plan_id"] == second["plan_id"]
    assert first["generated_at"] != ""
    assert second["generated_at"] != ""


def test_layout_plan_ignores_album_folder_for_nightcore_destinations(tmp_path):
    from pathlib import Path

    from app.logic.local_ai.config import LocalAIConfig
    from app.logic.local_ai.library_layout_planner import plan_library_layout

    path = tmp_path / "Kenke" / "Official Album" / "a.mp3"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"audio")
    track = _track(
        "Nightcore - A",
        artist="Kenke",
        album="Official Album",
        path=str(path),
        fileMtime=path.stat().st_mtime_ns,
        fileSize=path.stat().st_size,
    )
    track["album_kind"] = "official_or_existing"
    track["album_source"] = "existing"

    plan = plan_library_layout([track], music_dir=str(tmp_path), config=LocalAIConfig(), use_local_ai=False)

    assert Path(plan["moves"][0]["to"]).relative_to(tmp_path).parts == ("Nightcore", "Kenke", "a.mp3")


def test_layout_plan_file_path_only_duplicate_titles_are_order_independent(tmp_path):
    from app.logic.local_ai.config import LocalAIConfig
    from app.logic.local_ai.library_layout_planner import plan_library_layout

    first_path = tmp_path / "Old" / "Artist A" / "b.mp3"
    second_path = tmp_path / "Old" / "Artist A" / "a.mp3"
    for path in (first_path, second_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(path.name.encode("utf-8"))

    first_track = _track("Duplicate", artist="Artist A", path="", fileMtime=first_path.stat().st_mtime_ns, fileSize=first_path.stat().st_size)
    first_track.pop("path")
    first_track["file_path"] = str(first_path)
    second_track = _track(
        "Duplicate",
        artist="Artist A",
        path="",
        fileMtime=second_path.stat().st_mtime_ns,
        fileSize=second_path.stat().st_size,
    )
    second_track.pop("path")
    second_track["file_path"] = str(second_path)

    config = LocalAIConfig(model="qwen2.5:3b")
    first_plan = plan_library_layout([first_track, second_track], music_dir=str(tmp_path), config=config, use_local_ai=True)
    second_plan = plan_library_layout([second_track, first_track], music_dir=str(tmp_path), config=config, use_local_ai=True)

    assert first_plan["plan_id"] == second_plan["plan_id"]
    assert first_plan["tree"] == second_plan["tree"]
    assert first_plan["moves"] == second_plan["moves"]
    assert [track["path"] for track in first_plan["tree"][0]["artists"][0]["tracks"]] == [str(second_path), str(first_path)]


def test_save_layout_plan_rejects_malicious_plan_id(tmp_path):
    from app.logic.local_ai.library_layout_planner import save_layout_plan

    plan = {"plan_id": "../escape", "moves": [], "metadata_operations": [], "fingerprints": []}

    with pytest.raises(ValueError):
        save_layout_plan(plan, plan_dir=tmp_path / "plans")

    assert not (tmp_path / "escape.json").exists()


def test_load_layout_plan_rejects_malicious_plan_id(tmp_path):
    from app.logic.local_ai.library_layout_planner import load_layout_plan

    with pytest.raises(ValueError):
        load_layout_plan("../escape", plan_dir=tmp_path / "plans")


def test_apply_uses_saved_plan_and_detects_fingerprint_conflict(tmp_path, monkeypatch):
    from app.logic.local_ai.config import LocalAIConfig
    from app.logic.local_ai import library_layout_planner
    from app.logic.local_ai.library_layout_planner import apply_library_layout_plan, plan_library_layout, save_layout_plan

    path = tmp_path / "Kenke" / "Nightcore Covers" / "a.mp3"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"audio")
    track = _track(
        "Nightcore - A",
        artist="Kenke",
        path=str(path),
        fileMtime=path.stat().st_mtime_ns,
        fileSize=path.stat().st_size,
        videoId="abc123def45",
    )
    plan = plan_library_layout([track], music_dir=str(tmp_path), config=LocalAIConfig(model="qwen2.5:3b"), use_local_ai=True)
    plan_dir = tmp_path / "plans"
    manifest_dir = tmp_path / "manifests"
    save_layout_plan(plan, plan_dir=plan_dir)

    monkeypatch.setattr(
        library_layout_planner,
        "infer_library_group",
        lambda _: pytest.fail("apply must use the saved plan without reclassification"),
    )
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


def test_apply_detects_video_id_fingerprint_mismatch(tmp_path):
    from app.logic.local_ai.config import LocalAIConfig
    from app.logic.local_ai.library_layout_planner import apply_library_layout_plan, compute_plan_id, plan_library_layout, save_layout_plan

    path = tmp_path / "Kenke" / "Nightcore Covers" / "a.mp3"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"audio")
    track = _track(
        "Nightcore - A",
        artist="Kenke",
        path=str(path),
        fileMtime=path.stat().st_mtime_ns,
        fileSize=path.stat().st_size,
        videoId="abc123def45",
    )
    plan = plan_library_layout([track], music_dir=str(tmp_path), config=LocalAIConfig(), use_local_ai=False)
    mismatched_key = plan["fingerprints"][0]["track_key"].rsplit("|", 1)[0] + "|different-video"
    plan["fingerprints"][0]["track_key"] = mismatched_key
    plan["moves"][0]["track_key"] = mismatched_key
    plan["metadata_operations"][0]["track_key"] = mismatched_key
    plan["plan_id"] = compute_plan_id(plan)
    plan_dir = tmp_path / "plans"
    manifest_dir = tmp_path / "manifests"
    save_layout_plan(plan, plan_dir=plan_dir)

    result = apply_library_layout_plan(plan["plan_id"], current_music_dir=str(tmp_path), plan_dir=plan_dir, manifest_dir=manifest_dir)

    assert result["conflicts"] == 1
    assert result["files_moved"] == 0
    assert path.exists()
    manifest_text = next(manifest_dir.glob("*.json")).read_text(encoding="utf-8")
    assert "videoId fingerprint mismatch" in manifest_text


def test_apply_aborts_when_saved_plan_id_is_tampered(tmp_path):
    from app.logic.local_ai.config import LocalAIConfig
    from app.logic.local_ai.library_layout_planner import apply_library_layout_plan, plan_library_layout, save_layout_plan

    path = tmp_path / "Kenke" / "Nightcore Covers" / "a.mp3"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"audio")
    track = _track("Nightcore - A", artist="Kenke", path=str(path), fileMtime=path.stat().st_mtime_ns, fileSize=path.stat().st_size)
    plan = plan_library_layout([track], music_dir=str(tmp_path), config=LocalAIConfig(), use_local_ai=False)
    requested_plan_id = plan["plan_id"]
    plan_dir = tmp_path / "plans"
    manifest_dir = tmp_path / "manifests"
    save_layout_plan(plan, plan_dir=plan_dir)
    saved_path = plan_dir / f"{requested_plan_id}.json"
    saved = json.loads(saved_path.read_text(encoding="utf-8"))
    saved["plan_id"] = "0" * 16
    saved_path.write_text(json.dumps(saved), encoding="utf-8")

    result = apply_library_layout_plan(requested_plan_id, current_music_dir=str(tmp_path), plan_dir=plan_dir, manifest_dir=manifest_dir)

    assert result["errors"] == 1
    assert result["files_moved"] == 0
    assert path.exists()
    assert "plan_id" in result["message"]
    assert "plan_id" in next(manifest_dir.glob("*.json")).read_text(encoding="utf-8")


def test_apply_aborts_when_saved_plan_hash_is_tampered(tmp_path):
    from app.logic.local_ai.config import LocalAIConfig
    from app.logic.local_ai.library_layout_planner import apply_library_layout_plan, plan_library_layout, save_layout_plan

    path = tmp_path / "Kenke" / "Nightcore Covers" / "a.mp3"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"audio")
    track = _track("Nightcore - A", artist="Kenke", path=str(path), fileMtime=path.stat().st_mtime_ns, fileSize=path.stat().st_size)
    plan = plan_library_layout([track], music_dir=str(tmp_path), config=LocalAIConfig(), use_local_ai=False)
    plan_dir = tmp_path / "plans"
    manifest_dir = tmp_path / "manifests"
    save_layout_plan(plan, plan_dir=plan_dir)
    saved_path = plan_dir / f"{plan['plan_id']}.json"
    saved = json.loads(saved_path.read_text(encoding="utf-8"))
    saved["moves"][0]["to"] = str(tmp_path / "Nightcore" / "Kenke" / "tampered.mp3")
    saved_path.write_text(json.dumps(saved), encoding="utf-8")

    result = apply_library_layout_plan(plan["plan_id"], current_music_dir=str(tmp_path), plan_dir=plan_dir, manifest_dir=manifest_dir)

    assert result["errors"] == 1
    assert result["files_moved"] == 0
    assert path.exists()
    assert "integrity" in result["message"]
    assert "integrity" in next(manifest_dir.glob("*.json")).read_text(encoding="utf-8")


def test_apply_aborts_malformed_plan_and_writes_manifest(tmp_path):
    from app.logic.local_ai.config import LocalAIConfig
    from app.logic.local_ai.library_layout_planner import apply_library_layout_plan, compute_plan_id, plan_library_layout

    path = tmp_path / "Kenke" / "Nightcore Covers" / "a.mp3"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"audio")
    track = _track("Nightcore - A", artist="Kenke", path=str(path), fileMtime=path.stat().st_mtime_ns, fileSize=path.stat().st_size)
    plan = plan_library_layout([track], music_dir=str(tmp_path), config=LocalAIConfig(), use_local_ai=False)
    plan["moves"] = {"not": "a list"}
    plan["plan_id"] = compute_plan_id(plan)
    plan_dir = tmp_path / "plans"
    manifest_dir = tmp_path / "manifests"
    plan_dir.mkdir()
    (plan_dir / f"{plan['plan_id']}.json").write_text(json.dumps(plan), encoding="utf-8")

    result = apply_library_layout_plan(plan["plan_id"], current_music_dir=str(tmp_path), plan_dir=plan_dir, manifest_dir=manifest_dir)

    assert result["errors"] == 1
    assert result["files_moved"] == 0
    assert path.exists()
    assert "malformed" in result["message"]
    assert "malformed" in next(manifest_dir.glob("*.json")).read_text(encoding="utf-8")


def test_apply_move_exception_writes_manifest_error(tmp_path, monkeypatch):
    from app.logic.local_ai.config import LocalAIConfig
    from app.logic.local_ai import library_layout_planner
    from app.logic.local_ai.library_layout_planner import apply_library_layout_plan, plan_library_layout, save_layout_plan

    path = tmp_path / "Kenke" / "Nightcore Covers" / "a.mp3"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"audio")
    track = _track("Nightcore - A", artist="Kenke", path=str(path), fileMtime=path.stat().st_mtime_ns, fileSize=path.stat().st_size)
    plan = plan_library_layout([track], music_dir=str(tmp_path), config=LocalAIConfig(), use_local_ai=False)
    plan_dir = tmp_path / "plans"
    manifest_dir = tmp_path / "manifests"
    save_layout_plan(plan, plan_dir=plan_dir)

    def fail_move(*_args, **_kwargs):
        raise OSError("simulated move failure")

    monkeypatch.setattr(library_layout_planner.shutil, "move", fail_move)

    result = apply_library_layout_plan(plan["plan_id"], current_music_dir=str(tmp_path), plan_dir=plan_dir, manifest_dir=manifest_dir)

    assert result["errors"] == 1
    assert result["files_moved"] == 0
    assert path.exists()
    manifest = json.loads(next(manifest_dir.glob("*.json")).read_text(encoding="utf-8"))
    assert manifest["entries"][0]["status"] == "error"
    assert "simulated move failure" in manifest["entries"][0]["error"]


def test_apply_aborts_when_plan_file_has_corrupt_json(tmp_path):
    from app.logic.local_ai.library_layout_planner import apply_library_layout_plan

    plan_dir = tmp_path / "plans"
    plan_dir.mkdir(parents=True)
    manifest_dir = tmp_path / "manifests"
    (plan_dir / "abcd1234abcd1234.json").write_text("{invalid json}", encoding="utf-8")

    result = apply_library_layout_plan("abcd1234abcd1234", current_music_dir=str(tmp_path), plan_dir=plan_dir, manifest_dir=manifest_dir)

    assert result["errors"] == 1
    assert result["files_moved"] == 0
    manifest_file = next(manifest_dir.glob("*.json"), None)
    assert manifest_file is not None
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert any("JSON" in entry.get("error", "") or "json" in entry.get("error", "").lower() or "decode" in entry.get("error", "").lower() or "load" in entry.get("error", "").lower() for entry in manifest.get("entries", []))


def test_load_layout_plan_raises_on_corrupt_json_file(tmp_path):
    from app.logic.local_ai.library_layout_planner import load_layout_plan

    plan_dir = tmp_path / "plans"
    plan_dir.mkdir(parents=True)
    (plan_dir / "abcd1234abcd1234.json").write_text("{corrupt json}", encoding="utf-8")

    with pytest.raises(ValueError, match="malformed plan file|corrupt|JSON|decode|load"):
        load_layout_plan("abcd1234abcd1234", plan_dir=plan_dir)


def test_load_layout_plan_raises_on_missing_plan_file(tmp_path):
    from app.logic.local_ai.library_layout_planner import load_layout_plan

    plan_dir = tmp_path / "plans"
    plan_dir.mkdir(parents=True)

    with pytest.raises(ValueError, match="not found|missing|FileNotFoundError"):
        load_layout_plan("abcd1234abcd1234", plan_dir=plan_dir)


def test_write_library_layout_metadata_mp3_writes_custom_fields_without_album(tmp_path):
    from mutagen.id3 import ID3

    from app.logic.local_ai.enrichment_service import write_library_layout_metadata

    path = tmp_path / "song.mp3"
    path.write_bytes(b"\xff\xfb\x90\x00" * 200)

    written = write_library_layout_metadata(
        str(path),
        {"library_group": "Nightcore", "group_id": "group123", "collection": "Favorites"},
    )

    tags = ID3(str(path))
    assert set(written) == {"LOCAL_AI_LIBRARY_GROUP", "LOCAL_AI_GROUP_ID", "LOCAL_AI_COLLECTION"}
    assert str(tags.get("TXXX:LOCAL_AI_LIBRARY_GROUP").text[0]) == "Nightcore"
    assert str(tags.get("TXXX:LOCAL_AI_GROUP_ID").text[0]) == "group123"
    assert str(tags.get("TXXX:LOCAL_AI_COLLECTION").text[0]) == "Favorites"
    assert tags.get("TALB") is None


def test_read_library_layout_metadata_mp3_roundtrip(tmp_path):
    from app.logic.local_ai.enrichment_service import read_library_layout_metadata, write_library_layout_metadata

    path = tmp_path / "track.mp3"
    path.write_bytes(b"\xff\xfb\x90\x00" * 200)

    write_library_layout_metadata(
        str(path),
        {"library_group": "Electronic", "group_id": "gid_abc", "collection": "Workout"},
    )
    result = read_library_layout_metadata(str(path))
    assert result["library_group"] == "Electronic"
    assert result["group_id"] == "gid_abc"
    assert result["collection"] == "Workout"


def test_read_library_layout_metadata_mp4_roundtrip(tmp_path):
    from app.logic.local_ai.enrichment_service import read_library_layout_metadata, write_library_layout_metadata

    path = tmp_path / "track.m4a"
    _make_minimal_mp4(path)

    write_library_layout_metadata(
        str(path),
        {"library_group": "Rock Classics", "group_id": "gid_xyz", "collection": ""},
    )
    result = read_library_layout_metadata(str(path))
    assert result["library_group"] == "Rock Classics"
    assert result["group_id"] == "gid_xyz"
    assert result["collection"] == ""


def test_read_library_layout_metadata_returns_empty_when_no_tags(tmp_path):
    from app.logic.local_ai.enrichment_service import read_library_layout_metadata

    path = tmp_path / "clean.mp3"
    path.write_bytes(b"\xff\xfb\x90\x00" * 200)

    result = read_library_layout_metadata(str(path))
    assert result == {"library_group": "", "group_id": "", "collection": ""}


def test_read_library_layout_metadata_no_talb_interference(tmp_path):
    from mutagen.id3 import ID3, ID3NoHeaderError, TALB, TXXX

    from app.logic.local_ai.enrichment_service import read_library_layout_metadata

    path = tmp_path / "album_track.mp3"
    path.write_bytes(b"\xff\xfb\x90\x00" * 200)

    id3 = ID3()
    id3.add(TALB(encoding=3, text="Real Album"))
    id3.add(TXXX(encoding=3, desc="LOCAL_AI_LIBRARY_GROUP", text="Nightcore"))
    id3.save(str(path), v2_version=3, v1=2)

    result = read_library_layout_metadata(str(path))
    assert result["library_group"] == "Nightcore"
    assert result["group_id"] == ""
    assert result["collection"] == ""


def test_read_library_layout_metadata_mp4_invalid_file_returns_empty(tmp_path):
    from app.logic.local_ai.enrichment_service import read_library_layout_metadata

    path = tmp_path / "broken.m4a"
    path.write_bytes(b"not an mp4 file")

    result = read_library_layout_metadata(str(path))
    assert result == {"library_group": "", "group_id": "", "collection": ""}


def test_library_never_becomes_destination_group(tmp_path):
    from app.logic.local_ai.library_group_rules import fallback_group_for_track, infer_library_group, normalize_key

    track = {
        "title": "No Genre Track", "artist": "Unknown", "path": str(tmp_path / "noise.mp3"),
        "genre": "", "style": "", "tags": [], "source_title": "", "videoId": "",
        "semantic_profile": {
            "main_genre": "Unknown", "broad_genre": "Unknown",
            "style_markers": [], "context_markers": [],
            "performance_type": "studio", "likely_group_theme": "", "theme": "",
        },
    }

    fallback = fallback_group_for_track(track)
    assert normalize_key(fallback) in {"unknown", "library"}, f"fallback was '{fallback}'"

    result = infer_library_group(track)
    assert result["library_group"] == "", f"Expected empty group, got '{result['library_group']}'"
    assert result["library_group_source"] == ""


def test_legacy_ai_album_names_stripped_by_real_album(tmp_path):
    from app.logic.local_ai.library_layout_planner import _real_album

    ai_album_names = ["Alternative Rock", "Piano Covers", "Anime Soundtracks", "Pop", "Classical Piano"]
    for album in ai_album_names:
        assert _real_album({"album": album, "album_kind": "", "album_source": ""}) == "", (
            f"'{album}' should be detected as legacy AI album"
        )

    real_album_names = ["Hybrid Theory", "Meteora", "One More Light", "Random Access Memories"]
    for album in real_album_names:
        assert _real_album({"album": album, "album_kind": "", "album_source": ""}) == album, (
            f"'{album}' should be kept as real album"
        )


def test_duplicate_group_album_hierarchy_collapses(tmp_path):
    from app.logic.jellyfin_library import sanitize_component
    from app.logic.local_ai.config import LocalAIConfig
    from app.logic.local_ai.library_layout_planner import _destination_for_track

    track = {
        "title": "Song", "artist": "Artist", "album": "Electronic", "path": str(tmp_path / "old" / "song.mp3"),
        "fileMtime": 1, "fileSize": 100, "genre": "Electronic", "style": "", "tags": [],
        "source_title": "", "videoId": "", "album_kind": "", "album_source": "",
    }
    assignment = {"library_group": "Electronic", "library_group_source": "local_ai"}

    dest = _destination_for_track(track, assignment, music_dir=str(tmp_path))
    parts = Path(dest).relative_to(tmp_path).parts

    safe_artist = sanitize_component(track["artist"])
    assert len(parts) == 3, f"Expected 3 parts (group/artist/file), got {parts}"
    assert parts[0] == "Electronic"
    assert parts[1] == safe_artist
    assert parts[2] == "song.mp3"


def test_live_video_tracks_merge_to_dominant_group(tmp_path):
    from app.logic.local_ai.config import LocalAIConfig
    from app.logic.local_ai.library_layout_planner import plan_library_layout

    base_path = tmp_path / "Linkin Park"
    paths = {
        "electronic": base_path / "Electronic",
        "live": base_path / "Alternative Rock",
    }
    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)

    electronic1 = paths["electronic"] / "track1.mp3"
    electronic1.write_bytes(b"audio1")
    electronic2 = paths["electronic"] / "track2.mp3"
    electronic2.write_bytes(b"audio2")
    live_track = paths["live"] / "live_track.mp3"
    live_track.write_bytes(b"audio3")

    tracks = [
        {
            "title": "From The Inside", "artist": "Linkin Park", "path": str(electronic1),
            "fileMtime": electronic1.stat().st_mtime_ns, "fileSize": electronic1.stat().st_size,
            "genre": "Electronic", "style": "Electronic", "tags": [], "source_title": "", "videoId": "",
        },
        {
            "title": "The Emptiness Machine", "artist": "Linkin Park", "path": str(electronic2),
            "fileMtime": electronic2.stat().st_mtime_ns, "fileSize": electronic2.stat().st_size,
            "genre": "Electronic", "style": "Electronic", "tags": [], "source_title": "", "videoId": "",
        },
        {
            "title": "Cut the Bridge (Live)", "artist": "Linkin Park", "path": str(live_track),
            "fileMtime": live_track.stat().st_mtime_ns, "fileSize": live_track.stat().st_size,
            "genre": "Rock", "style": "Electronic", "tags": [], "source_title": "", "videoId": "",
        },
    ]

    plan = plan_library_layout(tracks, music_dir=str(tmp_path), config=LocalAIConfig(), use_local_ai=False)

    for group in plan["tree"]:
        if group["name"] == "Electronic":
            artist_names = [a["name"] for a in group["artists"]]
            assert "Linkin Park" in artist_names, "Electronic should contain Linkin Park"
            lp_artist = next(a for a in group["artists"] if a["name"] == "Linkin Park")
            assert lp_artist["track_count"] == 3, (
                f"All 3 Linkin Park tracks should merge to Electronic, got {lp_artist['track_count']}"
            )
            break
    else:
        pytest.fail("Expected Electronic group in plan tree")

    assert "Library" not in {g["name"] for g in plan["tree"]}, "Library must not appear as a group"


def test_insufficient_evidence_creates_conflict(tmp_path):
    from app.logic.local_ai.config import LocalAIConfig
    from app.logic.local_ai.library_layout_planner import plan_library_layout

    path = tmp_path / "Unknown" / "Artist" / "noise.mp3"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"unknown audio")

    track = {
        "title": "Noise", "artist": "Mystery", "path": str(path),
        "fileMtime": path.stat().st_mtime_ns, "fileSize": path.stat().st_size,
        "genre": "", "style": "", "tags": [], "source_title": "", "videoId": "",
        "semantic_profile": {
            "main_genre": "Unknown", "broad_genre": "Unknown",
            "style_markers": [], "context_markers": [],
            "performance_type": "studio", "likely_group_theme": "", "theme": "",
        },
    }

    plan = plan_library_layout([track], music_dir=str(tmp_path), config=LocalAIConfig(), use_local_ai=False)

    assert len(plan["conflicts"]) >= 1
    conflict = plan["conflicts"][0]
    assert conflict["type"] == "insufficient_library_group_evidence"
    assert "Noise" in conflict["message"]
    assert "Mystery" in conflict["message"]

    assert len(plan["moves"]) == 0, "No moves should be planned for insufficient evidence"
    assert len(plan["tree"]) == 0, "No tree entries for tracks without a valid group"


def test_legacy_ai_album_not_retained_in_destination(tmp_path):
    from app.logic.jellyfin_library import sanitize_component
    from app.logic.local_ai.config import LocalAIConfig
    from app.logic.local_ai.library_layout_planner import plan_library_layout

    source_dir = tmp_path / "AweSky" / "Anime Soundtracks"
    source_dir.mkdir(parents=True)
    mp3 = source_dir / "track.mp3"
    mp3.write_bytes(b"audio")

    track = {
        "title": "Middle Of The Night", "artist": "AweSky", "path": str(mp3),
        "album": "Anime Soundtracks",
        "fileMtime": mp3.stat().st_mtime_ns, "fileSize": mp3.stat().st_size,
        "genre": "Soundtrack", "style": "", "tags": ["anime"], "source_title": "", "videoId": "",
        "album_kind": "", "album_source": "",
    }

    plan = plan_library_layout([track], music_dir=str(tmp_path), config=LocalAIConfig(), use_local_ai=False)

    safe_artist = sanitize_component(track["artist"])
    assert len(plan["moves"]) == 1
    move = plan["moves"][0]
    to_path = Path(move["to"])
    parts = to_path.relative_to(tmp_path).parts

    assert parts[0] == "Anime Soundtracks", f"Group should be 'Anime Soundtracks', got {parts}"
    assert parts[1] == safe_artist, f"Artist should be '{safe_artist}', got {parts}"
    assert len(parts) == 3, (
        f"Destination should be group/artist/track (3 parts), got {len(parts)} parts: {parts}"
    )
    assert parts[2] == "track.mp3", f"Filename should be 'track.mp3', got {parts[2]}"


def test_piano_version_in_title_creates_piano_group_not_conflict(tmp_path):
    from app.logic.local_ai.config import LocalAIConfig
    from app.logic.local_ai.library_layout_planner import plan_library_layout

    path = tmp_path / "Grim Cat Piano" / "old_folder" / "track.mp3"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"piano audio")

    track = {
        "title": "I Really Want to Stay At Your House (Piano Version)",
        "artist": "Grim Cat Piano",
        "album": "Piano Covers",
        "path": str(path),
        "fileMtime": path.stat().st_mtime_ns,
        "fileSize": path.stat().st_size,
        "genre": "", "style": "", "tags": [], "source_title": "", "videoId": "",
        "semantic_profile": {
            "main_genre": "Unknown", "broad_genre": "Unknown",
            "style_markers": [], "context_markers": [],
            "performance_type": "studio", "likely_group_theme": "", "theme": "",
        },
    }

    plan = plan_library_layout([track], music_dir=str(tmp_path), config=LocalAIConfig(), use_local_ai=False)

    assert len(plan["conflicts"]) == 0, f"Got unexpected conflicts: {plan['conflicts']}"
    assert len(plan["moves"]) >= 1

    dest = Path(plan["moves"][0]["to"])
    parts = dest.relative_to(tmp_path).parts
    assert parts[0] == "Piano Covers", (
        f"Expected 'Piano Covers' group, got '{parts[0]}'"
    )
    assert "Cyberpunk" not in parts[0], "Group must not contain franchise/title tokens"


def test_rock_evidence_in_album_beats_electronic_fallback(tmp_path):
    from app.logic.jellyfin_library import sanitize_component
    from app.logic.local_ai.config import LocalAIConfig
    from app.logic.local_ai.library_layout_planner import plan_library_layout

    paths = {
        "r1": tmp_path / "Linkin Park" / "Alternative Rock" / "track1.mp3",
        "r2": tmp_path / "Linkin Park" / "Alternative Rock" / "track2.mp3",
        "live": tmp_path / "Linkin Park" / "Alternative Rock" / "live.mp3",
    }
    for p in paths.values():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"audio")

    tracks = [
        {
            "title": "From The Inside (Official Music Video)", "artist": "Linkin Park",
            "album": "Alternative Rock", "path": str(paths["r1"]),
            "fileMtime": paths["r1"].stat().st_mtime_ns,
            "fileSize": paths["r1"].stat().st_size,
            "genre": "Electronic", "style": "Electronic", "tags": [], "source_title": "", "videoId": "",
        },
        {
            "title": "The Emptiness Machine (Official Music Video)", "artist": "Linkin Park",
            "album": "Alternative Rock", "path": str(paths["r2"]),
            "fileMtime": paths["r2"].stat().st_mtime_ns,
            "fileSize": paths["r2"].stat().st_size,
            "genre": "Electronic", "style": "", "tags": [], "source_title": "", "videoId": "",
        },
        {
            "title": "Cut the Bridge (Live)", "artist": "Linkin Park",
            "album": "Alternative Rock", "path": str(paths["live"]),
            "fileMtime": paths["live"].stat().st_mtime_ns,
            "fileSize": paths["live"].stat().st_size,
            "genre": "", "style": "", "tags": [], "source_title": "", "videoId": "",
        },
    ]

    plan = plan_library_layout(tracks, music_dir=str(tmp_path), config=LocalAIConfig(), use_local_ai=False)

    assert len(plan["conflicts"]) == 0, f"Got unexpected conflicts: {plan['conflicts']}"

    electronic_groups = [g for g in plan["tree"] if g["name"] == "Electronic"]
    assert not electronic_groups, "Electronic must not appear as a group for Linkin Park"

    alt_rock_groups = [g for g in plan["tree"] if g["name"] in {"Alternative Rock", "Rock", "Rock-Pop"}]
    assert alt_rock_groups, f"Expected Alternative Rock/Rock/Rock-Pop in groups, got {[g['name'] for g in plan['tree']]}"

    lp_tracks = sum(
        a["track_count"]
        for g in plan["tree"]
        for a in g["artists"]
        if a["name"] == "Linkin Park"
    )
    assert lp_tracks == 3, f"All 3 Linkin Park tracks should be in one group, got {lp_tracks}"

    safe_artist = sanitize_component(tracks[0]["artist"])
    for move in plan["moves"]:
        to_path = Path(move["to"])
        parts = to_path.relative_to(tmp_path).parts
        assert len(parts) == 3, (
            f"Destination should be group/artist/track, got {parts}"
        )
        assert parts[1] == safe_artist, (
            f"Artist path component '{parts[1]}' does not match sanitized '{safe_artist}'"
        )
        assert parts[2] in {"track1.mp3", "track2.mp3", "live.mp3"}


def test_read_library_layout_metadata_unsupported_ext_returns_empty(tmp_path):
    from app.logic.local_ai.enrichment_service import read_library_layout_metadata

    path = tmp_path / "track.flac"
    path.write_bytes(b"fake flac")

    result = read_library_layout_metadata(str(path))
    assert result == {"library_group": "", "group_id": "", "collection": ""}


def test_safe_layout_path_blocks_path_traversal(tmp_path):
    from app.logic.local_ai.library_layout_planner import _safe_layout_path

    root_str = str(tmp_path.resolve())

    traversal_attempt = _safe_layout_path(root_str, "..", "escape")
    assert str(traversal_attempt).startswith(root_str)

    traversal_attempt2 = _safe_layout_path(root_str, "Group", "..", "..", "tmp", "file.mp3")
    assert str(traversal_attempt2).startswith(root_str)

    normal = _safe_layout_path(root_str, "Group", "Artist", "track.mp3")
    assert str(normal).startswith(root_str)


def test_within_root_rejects_outside_paths(tmp_path):
    import tempfile

    from app.logic.local_ai.library_layout_planner import _within_root

    root = tmp_path.resolve()

    other_root = Path(tempfile.mkdtemp())
    outside_file = other_root / "leak.txt"
    outside_file.write_bytes(b"data")

    assert _within_root(root / "Group" / "Artist" / "track.mp3", root)
    assert _within_root(root, root)
    assert not _within_root(outside_file, root)
    assert not _within_root(root / ".." / "etc" / "passwd", root)


def test_plan_does_not_mutate_filesystem(tmp_path):
    from app.logic.local_ai.config import LocalAIConfig
    from app.logic.local_ai.library_layout_planner import plan_library_layout

    path = tmp_path / "Artist" / "album" / "song.mp3"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"original audio content")
    original_content = path.read_bytes()
    original_mtime = path.stat().st_mtime_ns

    track = {
        "title": "Song",
        "artist": "Artist",
        "path": str(path),
        "fileMtime": original_mtime,
        "fileSize": path.stat().st_size,
        "genre": "Electronic",
        "style": "",
        "tags": [],
        "source_title": "",
        "videoId": "",
    }

    plan = plan_library_layout([track], music_dir=str(tmp_path), config=LocalAIConfig(), use_local_ai=False)

    assert path.read_bytes() == original_content
    assert path.stat().st_mtime_ns == original_mtime
    assert not (tmp_path / "data").exists()
    assert plan["plan_id"] != ""
    assert plan["moves"] is not None
    assert plan["metadata_operations"] is not None
    assert plan["fingerprints"] is not None


def test_apply_rejects_source_outside_library_root(tmp_path):
    from app.logic.local_ai.config import LocalAIConfig
    from app.logic.local_ai.library_layout_planner import (
        apply_library_layout_plan,
        compute_plan_id,
        plan_library_layout,
        save_layout_plan,
    )

    path = tmp_path / "Kenke" / "Nightcore Covers" / "a.mp3"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"audio")
    track = {
        "title": "Nightcore - A", "artist": "Kenke", "path": str(path),
        "fileMtime": path.stat().st_mtime_ns, "fileSize": path.stat().st_size,
        "genre": "Electronic", "style": "Nightcore", "tags": [], "source_title": "", "videoId": "",
    }
    plan = plan_library_layout([track], music_dir=str(tmp_path), config=LocalAIConfig(), use_local_ai=False)

    outside_file = tmp_path / ".." / "outside_music" / "a.mp3"
    outside_file.parent.mkdir(parents=True, exist_ok=True)
    outside_file.write_bytes(b"outside")
    plan["moves"][0]["from"] = str(outside_file)
    plan["moves"][0]["to"] = str(tmp_path / "Nightcore" / "Kenke" / "a.mp3")
    plan["plan_id"] = compute_plan_id(plan)

    plan_dir = tmp_path / "plans"
    manifest_dir = tmp_path / "manifests"
    save_layout_plan(plan, plan_dir=plan_dir)

    result = apply_library_layout_plan(
        plan["plan_id"], current_music_dir=str(tmp_path),
        plan_dir=plan_dir, manifest_dir=manifest_dir,
    )

    assert result["conflicts"] >= 1, (
        f"Expected at least 1 conflict for source outside root, got: {result}"
    )
    assert result["files_moved"] == 0


def test_apply_rejects_destination_outside_library_root(tmp_path):
    from app.logic.local_ai.config import LocalAIConfig
    from app.logic.local_ai.library_layout_planner import (
        apply_library_layout_plan,
        compute_plan_id,
        plan_library_layout,
        save_layout_plan,
    )

    path = tmp_path / "Kenke" / "Nightcore Covers" / "a.mp3"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"audio")
    track = {
        "title": "Nightcore - A", "artist": "Kenke", "path": str(path),
        "fileMtime": path.stat().st_mtime_ns, "fileSize": path.stat().st_size,
        "genre": "Electronic", "style": "Nightcore", "tags": [], "source_title": "", "videoId": "",
    }
    plan = plan_library_layout([track], music_dir=str(tmp_path), config=LocalAIConfig(), use_local_ai=False)

    outside_dest = tmp_path / ".." / "outside_music" / "Nightcore" / "Kenke" / "a.mp3"
    plan["moves"][0]["to"] = str(outside_dest)
    plan["plan_id"] = compute_plan_id(plan)

    plan_dir = tmp_path / "plans"
    manifest_dir = tmp_path / "manifests"
    save_layout_plan(plan, plan_dir=plan_dir)

    result = apply_library_layout_plan(
        plan["plan_id"], current_music_dir=str(tmp_path),
        plan_dir=plan_dir, manifest_dir=manifest_dir,
    )

    assert result["conflicts"] >= 1
    assert result["files_moved"] == 0


def test_apply_rejects_symlink_source_pointing_outside_root(tmp_path):
    from app.logic.local_ai.config import LocalAIConfig
    from app.logic.local_ai.library_layout_planner import (
        apply_library_layout_plan,
        compute_plan_id,
        plan_library_layout,
        save_layout_plan,
    )

    outside_file = tmp_path / "outside" / "real.mp3"
    outside_file.parent.mkdir(parents=True)
    outside_file.write_bytes(b"real audio")

    music_root = tmp_path / "music"
    music_root.mkdir()
    source_link = music_root / "Artist" / "song.mp3"
    source_link.parent.mkdir(parents=True)
    source_link.symlink_to(outside_file)

    track = {
        "title": "Song", "artist": "Artist", "path": str(source_link),
        "fileMtime": source_link.stat().st_mtime_ns,
        "fileSize": source_link.stat().st_size,
        "genre": "Electronic", "style": "", "tags": [], "source_title": "", "videoId": "",
    }

    plan = plan_library_layout([track], music_dir=str(music_root), config=LocalAIConfig(), use_local_ai=False)
    assert len(plan["moves"]) >= 1

    plan_dir = tmp_path / "plans"
    manifest_dir = tmp_path / "manifests"
    save_layout_plan(plan, plan_dir=plan_dir)

    result = apply_library_layout_plan(
        plan["plan_id"], current_music_dir=str(music_root),
        plan_dir=plan_dir, manifest_dir=manifest_dir,
    )

    assert result["conflicts"] >= 1, f"symlink source outside root should conflict, got: {result}"
    assert result["files_moved"] == 0
    manifest_files = list(manifest_dir.glob("*.json"))
    assert any("outside library_root" in f.read_text(encoding="utf-8") for f in manifest_files)


def test_apply_metadata_only_track_no_move(tmp_path, monkeypatch):
    from app.logic.local_ai.config import LocalAIConfig
    from app.logic.local_ai.library_layout_planner import (
        apply_library_layout_plan,
        plan_library_layout,
        save_layout_plan,
    )

    path = tmp_path / "Electronic" / "Artist" / "stay.mp3"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"audio")

    track = {
        "title": "Stay", "artist": "Artist", "path": str(path),
        "fileMtime": path.stat().st_mtime_ns, "fileSize": path.stat().st_size,
        "genre": "Electronic", "style": "", "tags": [], "source_title": "", "videoId": "",
    }

    plan = plan_library_layout([track], music_dir=str(tmp_path), config=LocalAIConfig(), use_local_ai=False)
    assert len(plan["moves"]) == 0, "track already in expected location should have no moves"
    assert len(plan["metadata_operations"]) == 1
    assert len(plan["fingerprints"]) == 1

    plan_dir = tmp_path / "plans"
    manifest_dir = tmp_path / "manifests"
    save_layout_plan(plan, plan_dir=plan_dir)

    called = []

    def fake_write_metadata(path_str, fields):
        called.append((path_str, dict(fields)))
        return ["LOCAL_AI_LIBRARY_GROUP"]

    import app.logic.local_ai.library_layout_planner as planner_mod
    monkeypatch.setattr(planner_mod, "_write_metadata_if_available", fake_write_metadata)

    result = apply_library_layout_plan(
        plan["plan_id"], current_music_dir=str(tmp_path),
        plan_dir=plan_dir, manifest_dir=manifest_dir,
    )

    assert result["errors"] == 0, f"metadata-only apply failed: {result}"
    assert result["files_moved"] == 0
    assert result["metadata_written"] >= 1, f"expected metadata write, got: {result}"
    assert result["applied"] >= 1
    assert len(called) == 1
    assert called[0][0] == str(path)
    assert called[0][1].get("LOCAL_AI_LIBRARY_GROUP") == "Electronic"


def test_apply_destination_already_exists_creates_duplicate(tmp_path):
    from app.logic.local_ai.config import LocalAIConfig
    from app.logic.local_ai.library_layout_planner import (
        apply_library_layout_plan,
        plan_library_layout,
        save_layout_plan,
    )

    source = tmp_path / "Artist" / "album" / "move_me.mp3"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"source audio")

    existing = tmp_path / "Electronic" / "Artist" / "move_me.mp3"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"existing destination audio")

    track = {
        "title": "move_me", "artist": "Artist", "path": str(source),
        "fileMtime": source.stat().st_mtime_ns, "fileSize": source.stat().st_size,
        "genre": "Electronic", "style": "", "tags": [], "source_title": "", "videoId": "",
    }

    plan = plan_library_layout([track], music_dir=str(tmp_path), config=LocalAIConfig(), use_local_ai=False)
    assert len(plan["moves"]) >= 1

    plan_dir = tmp_path / "plans"
    manifest_dir = tmp_path / "manifests"
    save_layout_plan(plan, plan_dir=plan_dir)

    result = apply_library_layout_plan(
        plan["plan_id"], current_music_dir=str(tmp_path),
        plan_dir=plan_dir, manifest_dir=manifest_dir,
    )

    assert result["errors"] == 0, f"duplicate apply failed: {result}"
    assert result["files_moved"] == 1
    assert not source.exists(), "source should have been moved"

    expected_duplicate = tmp_path / "Electronic" / "Artist" / "move_me (1).mp3"
    assert expected_duplicate.exists(), f"expected duplicate at {expected_duplicate}"
    assert expected_duplicate.stat().st_size > 0
    assert not source.exists(), "source should have been moved"
    assert existing.read_bytes() == b"existing destination audio", "original remained unchanged"


def test_apply_missing_plan_file_aborts_with_manifest(tmp_path):
    from app.logic.local_ai.library_layout_planner import apply_library_layout_plan

    manifest_dir = tmp_path / "manifests"
    plan_dir = tmp_path / "plans"
    plan_dir.mkdir(parents=True)

    result = apply_library_layout_plan(
        "abcd1234abcd1234", current_music_dir=str(tmp_path),
        plan_dir=plan_dir, manifest_dir=manifest_dir,
    )

    assert result["errors"] == 1
    assert result["files_moved"] == 0
    assert "not found" in result.get("message", "").lower() or "not found" in str(result)

    manifest_files = list(manifest_dir.glob("*.json"))
    assert manifest_files, "manifest should be written even on abort"
    manifest_text = manifest_files[0].read_text(encoding="utf-8")
    assert "not found" in manifest_text.lower()
