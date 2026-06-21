from __future__ import annotations

from pathlib import Path


def _profile(**kwargs):
    return {
        "main_genre": kwargs.get("genre", "Electronic"),
        "broad_genre": kwargs.get("genre", "Electronic"),
        "style_markers": kwargs.get("style_markers", []),
        "context_markers": kwargs.get("context_markers", []),
        "performance_type": kwargs.get("performance_type", "studio"),
        "likely_group_theme": kwargs.get("theme", ""),
        "theme": kwargs.get("theme", ""),
    }


def _track(title: str, artist: str = "Artist A", **kwargs):
    profile = kwargs.get("semantic_profile") or _profile(
        genre=kwargs.get("genre", "Electronic"),
        style_markers=kwargs.get("style_markers", [kwargs["style"].lower()] if kwargs.get("style") else ["nightcore"]),
        context_markers=kwargs.get("context_markers", []),
        performance_type=kwargs.get("performance_type", "studio"),
        theme=kwargs.get("likely_group_theme", "nightcore electronic"),
    )
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
        "semantic_profile": profile,
    }


def test_prefers_fewer_groups_over_many_small_groups(tmp_path):
    from app.logic.local_ai.album_group_planner import plan_library_album_groups
    from app.logic.local_ai.config import LocalAIConfig

    config = LocalAIConfig(album_groups_registry_path=str(tmp_path / "groups.json"))
    tracks = [
        _track("Nightcore - A", artist="Kenke", path="/music/Kenke/a.mp3"),
        _track("Nightcore - B", artist="Kenke", path="/music/Kenke/b.mp3"),
        _track("Nightcore - C", artist="Kenke", path="/music/Kenke/c.mp3"),
    ]
    plan = plan_library_album_groups(tracks, config=config, rebuild=True, use_local_ai=False, persist_registry=False)
    artist_groups = [group for group in plan["groups"] if group["artist_scope"] == "Kenke"]
    assert len(artist_groups) == 1
    assert artist_groups[0]["name"] == "Nightcore"


def test_live_video_lyrics_amv_do_not_split_groups(tmp_path):
    from app.logic.local_ai.album_group_planner import plan_library_album_groups
    from app.logic.local_ai.config import LocalAIConfig

    config = LocalAIConfig(album_groups_registry_path=str(tmp_path / "groups.json"))
    tracks = [
        _track(
            "Rock Song",
            artist="Band X",
            genre="Rock",
            style_markers=["rock"],
            path="/music/Band X/a.mp3",
            performance_type="studio",
            theme="alternative rock",
        ),
        _track(
            "Rock Song (Live)",
            artist="Band X",
            genre="Rock",
            style="Live",
            style_markers=["rock"],
            path="/music/Band X/b.mp3",
            performance_type="live",
            theme="alternative rock",
        ),
        _track(
            "Rock Song (Official Video)",
            artist="Band X",
            genre="Rock",
            style_markers=["rock"],
            context_markers=["music video"],
            path="/music/Band X/c.mp3",
            performance_type="video",
            theme="alternative rock",
        ),
    ]
    plan = plan_library_album_groups(tracks, config=config, rebuild=True, use_local_ai=False, persist_registry=False)
    albums = {assignment["album"] for assignment in plan["assignments"].values()}
    assert len(albums) == 1


def test_similar_tracks_same_artist_merge_to_one_group(tmp_path):
    from app.logic.local_ai.album_group_planner import plan_library_album_groups
    from app.logic.local_ai.config import LocalAIConfig

    config = LocalAIConfig(album_groups_registry_path=str(tmp_path / "groups.json"))
    tracks = [
        _track("Nightcore - A", artist="Eiden XII", path="/music/Eiden XII/a.mp3"),
        _track("Nightcore - B (Rock Version)", artist="Eiden XII", path="/music/Eiden XII/b.mp3"),
    ]
    plan = plan_library_album_groups(tracks, config=config, rebuild=True, use_local_ai=False, persist_registry=False)
    albums = {assignment["album"] for assignment in plan["assignments"].values()}
    assert len(albums) == 1
    assert "Nightcore" in next(iter(albums))


def test_group_name_does_not_contain_artist_name():
    from app.logic.local_ai.album_group_canonical import canonicalize_group_name, is_weak_group_name

    profiles = [_profile(genre="Electronic", style_markers=["nightcore"], theme="nightcore")]
    assert is_weak_group_name("Linkin Park Rock", profiles=profiles, artist="Linkin Park")
    assert canonicalize_group_name("Eiden XII Rock Nightcore", profiles) == "Nightcore"


def test_group_name_does_not_contain_full_title():
    from app.logic.local_ai.album_group_validator import validate_group_name

    track = {"title": "Nightcore - Alpha", "artist": "Artist A"}
    profiles = [_profile(style_markers=["nightcore"], theme="nightcore")]
    assert validate_group_name("Nightcore - Alpha", profiles=profiles, track=track, artist="Artist A") == "Nightcore"


def test_singles_and_unknown_album_are_not_final_names():
    from app.logic.local_ai.album_group_canonical import is_weak_group_name

    profiles = [_profile(style_markers=["nightcore"])]
    assert is_weak_group_name("Singles", profiles=profiles)
    assert is_weak_group_name("Unknown Album", profiles=profiles)


def test_music_video_rock_is_rejected():
    from app.logic.local_ai.album_group_canonical import is_weak_group_name

    profiles = [_profile(genre="Rock", style_markers=["rock"])]
    assert is_weak_group_name("Music Video Rock", profiles=profiles)


def test_cyberpunk_piano_is_rejected_for_single_track_context():
    from app.logic.local_ai.album_group_canonical import canonicalize_group_name

    profiles = [_profile(genre="Soundtrack", style_markers=["piano"], context_markers=[], theme="cyberpunk piano")]
    assert canonicalize_group_name("Cyberpunk Piano", profiles) == "Piano Covers"


def test_allowed_final_group_names():
    from app.logic.local_ai.album_group_canonical import build_group_name_from_cluster, is_weak_group_name

    assert not is_weak_group_name("Nightcore", profiles=[_profile(style_markers=["nightcore"])])
    assert build_group_name_from_cluster([_profile(genre="Rock", style_markers=["rock"])]) == "Alternative Rock"
    assert build_group_name_from_cluster([_profile(style_markers=["piano"])]) == "Piano Covers"
    assert build_group_name_from_cluster(
        [_profile(genre="Soundtrack", style_markers=["piano"], context_markers=["anime"])]
    ) == "Anime Piano"


def test_same_data_two_runs_are_identical(tmp_path):
    from app.logic.local_ai.album_group_planner import plan_library_album_groups
    from app.logic.local_ai.config import LocalAIConfig

    config = LocalAIConfig(album_groups_registry_path=str(tmp_path / "groups.json"))
    tracks = [
        _track("Nightcore - A", artist="Kenke", path="/music/Kenke/a.mp3"),
        _track("Piano Song", artist="Grim Cat Piano", genre="Soundtrack", style="Piano", style_markers=["piano"], path="/music/Grim/b.mp3"),
    ]
    first = plan_library_album_groups(tracks, config=config, rebuild=True, use_local_ai=False, persist_registry=False)
    second = plan_library_album_groups(list(reversed(tracks)), config=config, rebuild=True, use_local_ai=False, persist_registry=False)
    assert [group["name"] for group in first["groups"]] == [group["name"] for group in second["groups"]]


def test_production_code_has_no_artist_specific_mapping():
    classifier_dir = Path(__file__).resolve().parents[1] / "logic" / "local_ai"
    production_files = [
        classifier_dir / "album_group_planner.py",
        classifier_dir / "album_group_validator.py",
        classifier_dir / "album_group_canonical.py",
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


def test_plan_album_groups_does_not_write_or_move(tmp_path, monkeypatch):
    from app.logic.local_ai import enrichment_service

    captured: dict[str, object] = {}

    monkeypatch.setattr(enrichment_service, "write_audio_metadata", lambda *args, **kwargs: captured.setdefault("write", True))
    monkeypatch.setattr(enrichment_service, "move_track_to_album_folder", lambda *args, **kwargs: captured.setdefault("move", True))
    monkeypatch.setattr(enrichment_service, "scan_music_files", lambda _dir: [_track("Nightcore - Alpha", path=str(tmp_path / "song.mp3"))])
    monkeypatch.setattr(enrichment_service.JellyfinConfig, "get_music_library_path", lambda: str(tmp_path))
    monkeypatch.setattr(enrichment_service, "enrich_track_metadata", lambda track, **kwargs: _track("Nightcore - Alpha", path=track["path"]))

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


def test_linkin_park_like_tracks_merge_to_alternative_rock(tmp_path):
    from app.logic.local_ai.album_group_planner import plan_library_album_groups
    from app.logic.local_ai.config import LocalAIConfig

    config = LocalAIConfig(album_groups_registry_path=str(tmp_path / "groups.json"))
    tracks = [
        _track(
            "Cut the Bridge (Live) - Linkin Park",
            artist="Linkin Park",
            album="Live Electronic Dance",
            genre="Electronic",
            style="Live",
            style_markers=["electronic", "dance"],
            path="/music/Linkin Park/a.mp3",
            performance_type="live",
        ),
        _track(
            "The Emptiness Machine (Official Music Video) - Linkin Park",
            artist="Linkin Park",
            album="Music Video Electronic Dance",
            genre="Electronic",
            style_markers=["electronic", "dance"],
            context_markers=["music video"],
            path="/music/Linkin Park/b.mp3",
            performance_type="video",
        ),
        _track(
            "From The Inside (Official Music Video) - Linkin Park",
            artist="Linkin Park",
            album="Music Video Rock",
            genre="Rock",
            style_markers=["rock"],
            context_markers=["music video"],
            path="/music/Linkin Park/c.mp3",
            performance_type="video",
        ),
    ]
    plan = plan_library_album_groups(tracks, config=config, rebuild=True, use_local_ai=False, persist_registry=False)
    albums = {assignment["album"] for assignment in plan["assignments"].values()}
    assert len(albums) == 1
    assert next(iter(albums)) == "Alternative Rock"


def test_anime_mix_amv_maps_to_anime_soundtracks(tmp_path):
    from app.logic.local_ai.album_group_planner import plan_library_album_groups
    from app.logic.local_ai.config import LocalAIConfig

    config = LocalAIConfig(album_groups_registry_path=str(tmp_path / "groups.json"))
    track = _track(
        "Middle of the Night「AMV」Anime Mix",
        artist="TumpyGFX",
        album="Soundtrack AMV",
        genre="Soundtrack",
        style_markers=[],
        context_markers=["anime", "soundtrack"],
        path="/music/TumpyGFX/a.mp3",
        performance_type="video",
        theme="anime soundtrack",
    )
    plan = plan_library_album_groups([track], config=config, rebuild=True, use_local_ai=False, persist_registry=False)
    assert next(iter(plan["assignments"].values()))["album"] == "Anime Soundtracks"


def test_piano_anime_beats_spurious_nightcore_marker(tmp_path):
    from app.logic.local_ai.album_group_planner import plan_library_album_groups
    from app.logic.local_ai.config import LocalAIConfig

    config = LocalAIConfig(album_groups_registry_path=str(tmp_path / "groups.json"))
    track = _track(
        "Tokyo Ghoul OP - Unravel [Piano/Animenz arr.]",
        artist="Luminote",
        album="Tokyo Ghoul OP Piano Arr",
        genre="Soundtrack",
        style="Piano",
        style_markers=["piano", "electronic", "nightcore"],
        context_markers=["anime", "soundtrack"],
        path="/music/Luminote/a.mp3",
        performance_type="cover",
        theme="anime piano arrangements",
    )
    plan = plan_library_album_groups([track], config=config, rebuild=True, use_local_ai=False, persist_registry=False)
    assert next(iter(plan["assignments"].values()))["album"] == "Anime Piano"


def test_ai_managed_folders_are_repairable():
    from app.logic.local_ai.album_group_validator import is_repairable_source_album_folder

    assert is_repairable_source_album_folder("Music Video Rock")
    assert is_repairable_source_album_folder("Live Electronic Dance")
    assert is_repairable_source_album_folder("Soundtrack AMV")
    assert is_repairable_source_album_folder("Cyberpunk Piano")
    assert not is_repairable_source_album_folder("Hybrid Theory")


def test_existing_official_album_stays_untouched(tmp_path):
    from app.logic.local_ai.album_group_planner import plan_library_album_groups
    from app.logic.local_ai.config import LocalAIConfig

    config = LocalAIConfig(album_groups_registry_path=str(tmp_path / "groups.json"))
    track = _track("Song", artist="Band Y", album="Hybrid Theory", genre="Rock", path="/music/Band Y/Hybrid Theory/Song.mp3")
    plan = plan_library_album_groups([track], config=config, rebuild=True, use_local_ai=False, persist_registry=False)
    key = next(iter(plan["assignments"]))
    assert plan["assignments"][key]["album"] == "Hybrid Theory"
    assert plan["assignments"][key]["album_kind"] == "official_or_existing"
