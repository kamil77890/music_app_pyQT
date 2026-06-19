from __future__ import annotations

from pathlib import Path


def _track(title: str, artist: str = "Artist A", **kwargs):
    return {
        "title": title,
        "artist": artist,
        "album": kwargs.get("album", "Unknown Album"),
        "genre": kwargs.get("genre", "Electronic"),
        "style": kwargs.get("style"),
        "tags": kwargs.get("tags", []),
        "path": kwargs.get("path", f"/music/{artist}/{title}.mp3"),
        "fileMtime": kwargs.get("fileMtime", "1"),
        "fileSize": kwargs.get("fileSize", "100"),
        "videoId": kwargs.get("videoId", ""),
        "semantic_profile": kwargs.get(
            "semantic_profile",
            {
                "main_genre": kwargs.get("genre", "Electronic"),
                "style_markers": [kwargs["style"].lower()] if kwargs.get("style") else ["nightcore"],
                "context_markers": kwargs.get("context_markers", []),
                "performance_type": kwargs.get("performance_type", "studio"),
                "likely_group_theme": kwargs.get("likely_group_theme", "nightcore electronic"),
            },
        ),
    }


def test_no_closed_allowlist_blocks_dynamic_group_names():
    from app.logic.local_ai.album_group_validator import validate_group_name

    profile = {
        "main_genre": "Electronic",
        "style_markers": ["nightcore"],
        "context_markers": [],
        "performance_type": "studio",
        "likely_group_theme": "nightcore electronic covers",
    }
    name = validate_group_name("Electronic Nightcore", profile=profile)
    assert name == "Electronic Nightcore"
    name = validate_group_name("Anime Piano Arrangements", profile=profile)
    assert name == "Anime Piano Arrangements"


def test_production_code_has_no_artist_specific_mapping():
    classifier_dir = Path(__file__).resolve().parents[1] / "logic" / "local_ai"
    production_files = [
        classifier_dir / "album_group_planner.py",
        classifier_dir / "album_group_validator.py",
        classifier_dir / "album_group_registry.py",
        classifier_dir / "semantic_profile.py",
        classifier_dir / "enrichment_service.py",
        classifier_dir / "fallback_classifier.py",
        classifier_dir / "ollama_classifier.py",
    ]
    forbidden = ['if artist == "', "if artist == '", '== "Linkin Park"', '== "Kenke"']
    for file_path in production_files:
        source = file_path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in source, f"{token} found in {file_path.name}"


def test_same_library_different_order_gives_identical_group_plan(tmp_path, monkeypatch):
    from app.logic.local_ai.album_group_planner import plan_library_album_groups
    from app.logic.local_ai.config import LocalAIConfig

    config = LocalAIConfig(
        metadata_enabled=False,
        album_groups_registry_path=str(tmp_path / "groups.json"),
    )
    tracks_a = [
        _track("Nightcore - Alpha", path="/music/A/Alpha.mp3", likely_group_theme="nightcore electronic"),
        _track("Nightcore - Beta", path="/music/A/Beta.mp3", likely_group_theme="nightcore electronic"),
        _track("Piano Version Song", artist="Artist B", genre="Classical", style="Piano", path="/music/B/Piano.mp3", likely_group_theme="classical piano"),
    ]
    tracks_b = list(reversed(tracks_a))
    plan_a = plan_library_album_groups(tracks_a, config=config, rebuild=True, use_local_ai=False, persist_registry=False)
    plan_b = plan_library_album_groups(tracks_b, config=config, rebuild=True, use_local_ai=False, persist_registry=False)
    assert [group["name"] for group in plan_a["groups"]] == [group["name"] for group in plan_b["groups"]]
    assert plan_a["assignments"].keys() == plan_b["assignments"].keys()


def test_same_track_twice_gives_same_group_id_and_name(tmp_path):
    from app.logic.local_ai.album_group_planner import plan_library_album_groups
    from app.logic.local_ai.config import LocalAIConfig

    config = LocalAIConfig(album_groups_registry_path=str(tmp_path / "groups.json"))
    track = _track("Nightcore - Alpha", path="/music/A/Alpha.mp3")
    first = plan_library_album_groups([track], config=config, rebuild=True, use_local_ai=False, persist_registry=False)
    second = plan_library_album_groups([track], config=config, rebuild=True, use_local_ai=False, persist_registry=False)
    key = next(iter(first["assignments"]))
    assert first["assignments"][key]["group_id"] == second["assignments"][key]["group_id"]
    assert first["assignments"][key]["album"] == second["assignments"][key]["album"]


def test_live_track_can_share_group_with_similar_semantic_profile(tmp_path):
    from app.logic.local_ai.album_group_planner import plan_library_album_groups
    from app.logic.local_ai.config import LocalAIConfig

    config = LocalAIConfig(album_groups_registry_path=str(tmp_path / "groups.json"))
    tracks = [
        _track(
            "Alternative Song",
            artist="Band X",
            genre="Rock",
            style="Rock",
            path="/music/Band X/Studio.mp3",
            likely_group_theme="alternative rock",
            semantic_profile={
                "main_genre": "Rock",
                "style_markers": ["rock"],
                "context_markers": [],
                "performance_type": "studio",
                "likely_group_theme": "alternative rock",
            },
        ),
        _track(
            "Alternative Song (Live)",
            artist="Band X",
            genre="Rock",
            style="Live",
            path="/music/Band X/Live.mp3",
            performance_type="live",
            likely_group_theme="alternative rock",
            semantic_profile={
                "main_genre": "Rock",
                "style_markers": ["rock", "live"],
                "context_markers": [],
                "performance_type": "live",
                "likely_group_theme": "alternative rock",
            },
        ),
    ]
    plan = plan_library_album_groups(tracks, config=config, rebuild=True, use_local_ai=False, persist_registry=False)
    albums = {assignment["album"] for assignment in plan["assignments"].values()}
    assert len(albums) == 1
    live_assignment = next(value for value in plan["assignments"].values() if value.get("collection") == "Live")
    assert live_assignment["album_kind"] == "inferred_library_group"


def test_different_semantic_tracks_can_split_into_two_groups(tmp_path):
    from app.logic.local_ai.album_group_planner import plan_library_album_groups
    from app.logic.local_ai.config import LocalAIConfig

    config = LocalAIConfig(album_groups_registry_path=str(tmp_path / "groups.json"))
    tracks = [
        _track("Nightcore Song", artist="Artist C", path="/music/C/1.mp3", likely_group_theme="nightcore electronic"),
        _track(
            "Piano Song",
            artist="Artist C",
            genre="Classical",
            style="Piano",
            path="/music/C/2.mp3",
            likely_group_theme="classical piano",
            semantic_profile={
                "main_genre": "Classical",
                "style_markers": ["piano"],
                "context_markers": [],
                "performance_type": "studio",
                "likely_group_theme": "classical piano",
            },
        ),
    ]
    plan = plan_library_album_groups(tracks, config=config, rebuild=True, use_local_ai=False, persist_registry=False)
    albums = {assignment["album"] for assignment in plan["assignments"].values()}
    assert len(albums) == 2


def test_weak_generic_group_names_are_rejected():
    from app.logic.local_ai.album_group_validator import is_weak_group_name, validate_group_name

    profile = {
        "main_genre": "Electronic",
        "style_markers": ["nightcore"],
        "context_markers": [],
        "performance_type": "studio",
        "likely_group_theme": "nightcore electronic",
    }
    for bad in ["Singles", "Unknown Album", "Misc", "General Music", "Nightcore Collection"]:
        assert is_weak_group_name(bad)
        fixed = validate_group_name(bad, profile=profile)
        assert fixed not in {"Singles", "Unknown Album", "Misc", "General Music", "Nightcore Collection"}


def test_group_name_cannot_equal_title_or_artist():
    from app.logic.local_ai.album_group_validator import validate_group_name

    track = {"title": "Nightcore - Alpha", "artist": "Artist A"}
    profile = {
        "main_genre": "Electronic",
        "style_markers": ["nightcore"],
        "context_markers": [],
        "performance_type": "studio",
        "likely_group_theme": "nightcore electronic",
    }
    assert validate_group_name("Nightcore - Alpha", profile=profile, track=track, artist="Artist A") != "Nightcore - Alpha"
    assert validate_group_name("Artist A", profile=profile, track=track, artist="Artist A") != "Artist A"


def test_folder_move_is_safe_and_blocks_path_traversal(tmp_path):
    from app.logic.local_ai.enrichment_service import move_track_to_album_folder, plan_track_album_move

    lib = tmp_path / "music"
    source_dir = lib / "Artist A" / "Singles"
    source_dir.mkdir(parents=True)
    song = source_dir / "01 - Song.mp3"
    song.write_bytes(b"fake")
    existing = lib / "Artist A" / "Electronic Nightcore" / "01 - Song.mp3"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"existing")

    result = move_track_to_album_folder(
        path=str(song),
        artist="Artist A",
        target_album="Electronic Nightcore",
        music_dir=str(lib),
        dry_run=False,
    )
    assert result is not None
    assert result["to"].endswith("01 - Song (1).mp3")
    assert existing.read_bytes() == b"existing"
    assert plan_track_album_move(path=str(tmp_path / "outside.mp3"), artist="Artist A", target_album="Group", music_dir=str(lib)) is None


def test_plan_album_groups_does_not_write_or_move(tmp_path, monkeypatch):
    from app.logic.local_ai import enrichment_service

    captured: dict[str, object] = {}

    def fake_write(*args, **kwargs):
        captured["write"] = True

    def fake_move(*args, **kwargs):
        captured["move"] = True
        return None

    monkeypatch.setattr(enrichment_service, "write_audio_metadata", fake_write)
    monkeypatch.setattr(enrichment_service, "move_track_to_album_folder", fake_move)
    monkeypatch.setattr(enrichment_service, "scan_music_files", lambda _dir: [_track("Nightcore - Alpha", path=str(tmp_path / "song.mp3"))])
    monkeypatch.setattr(enrichment_service.JellyfinConfig, "get_music_library_path", lambda: str(tmp_path))

    def fake_enrich(track, **kwargs):
        return _track("Nightcore - Alpha", path=track["path"])

    monkeypatch.setattr(enrichment_service, "enrich_track_metadata", fake_enrich)

    summary = enrichment_service.enrich_library_batch(
        music_dir=str(tmp_path),
        plan_album_groups=True,
        rebuild_album_groups=True,
        force_local_ai=False,
        dry_run=True,
    )
    assert summary["plan_album_groups"] is True
    assert "album_group_plan_text" in summary
    assert "write" not in captured
    assert "move" not in captured


def test_rebuild_album_groups_creates_stable_plan(tmp_path):
    from app.logic.local_ai.album_group_planner import plan_library_album_groups
    from app.logic.local_ai.config import LocalAIConfig

    config = LocalAIConfig(album_groups_registry_path=str(tmp_path / "groups.json"))
    tracks = [_track("Nightcore - Alpha", path="/music/A/Alpha.mp3")]
    first = plan_library_album_groups(tracks, config=config, rebuild=True, use_local_ai=False, persist_registry=True)
    second = plan_library_album_groups(tracks, config=config, rebuild=False, use_local_ai=False, persist_registry=True)
    key = next(iter(first["assignments"]))
    assert second["assignments"][key]["album"] == first["assignments"][key]["album"]
    assert second["assignments"][key]["group_id"] == first["assignments"][key]["group_id"]


def test_existing_official_album_stays_untouched(tmp_path):
    from app.logic.local_ai.album_group_planner import plan_library_album_groups
    from app.logic.local_ai.config import LocalAIConfig

    config = LocalAIConfig(album_groups_registry_path=str(tmp_path / "groups.json"))
    track = _track("Song", artist="Band Y", album="Hybrid Theory", genre="Rock", path="/music/Band Y/Hybrid Theory/Song.mp3")
    plan = plan_library_album_groups([track], config=config, rebuild=True, use_local_ai=False, persist_registry=False)
    key = next(iter(plan["assignments"]))
    assert plan["assignments"][key]["album"] == "Hybrid Theory"
    assert plan["assignments"][key]["album_kind"] == "official_or_existing"
