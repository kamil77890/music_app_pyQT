from __future__ import annotations

import json


def test_unknown_album_nightcore_title_gets_nightcore_collection():
    from app.logic.local_ai.album_validator import resolve_track_album

    album, source, confidence = resolve_track_album(
        track={"title": "Nightcore - Hate Me", "artist": "Artist", "album": "Unknown Album"},
        genre="Electronic",
        style="Nightcore",
        tags=["Nightcore"],
    )

    assert album == "Nightcore Collection"
    assert source in {"fallback", "local_ai"}
    assert confidence > 0


def test_unknown_album_rock_version_gets_rock_versions():
    from app.logic.local_ai.album_validator import resolve_track_album

    album, _, _ = resolve_track_album(
        track={"title": "Song (Rock Version)", "artist": "Artist", "album": ""},
        genre="Rock",
        tags=["Rock"],
    )

    assert album == "Rock Versions"


def test_unknown_album_piano_version_gets_piano_versions():
    from app.logic.local_ai.album_validator import resolve_track_album

    album, _, _ = resolve_track_album(
        track={"title": "Song Piano Version", "artist": "Artist", "album": "Unknown Album"},
        genre="Unknown Genre",
        style="Piano",
    )

    assert album == "Piano Versions"


def test_unknown_album_ost_piano_gets_ost_collection():
    from app.logic.local_ai.album_validator import resolve_track_album

    album, _, _ = resolve_track_album(
        track={"title": "Solo Leveling Episode 6 OST Piano", "artist": "Artist", "album": ""},
        genre="Soundtrack",
        style="Piano",
        tags=["OST"],
    )

    assert album in {"OST Collection", "Soundtrack Collection", "Anime Soundtracks"}


def test_unknown_album_official_music_video_gets_music_videos():
    from app.logic.local_ai.album_validator import resolve_track_album

    album, _, _ = resolve_track_album(
        track={"title": "Avril Lavigne - Complicated (Official Video)", "artist": "Avril Lavigne", "album": ""},
        genre="Pop",
    )

    assert album in {"Music Videos", "Singles", "Pop Collection"}


def test_unknown_album_classical_piano_gets_classical_piano():
    from app.logic.local_ai.album_validator import resolve_track_album

    album, _, _ = resolve_track_album(
        track={"title": "Beethoven - Moonlight Sonata Piano", "artist": "Artist", "album": "Unknown Album"},
        genre="Classical",
        style="Piano",
    )

    assert album == "Classical Piano"


def test_unknown_album_no_evidence_gets_singles():
    from app.logic.local_ai.album_validator import resolve_track_album

    album, source, _ = resolve_track_album(
        track={"title": "Random Track Name", "artist": "Some Artist", "album": "Unknown Album"},
        genre="Unknown Genre",
    )

    assert album == "Singles"
    assert source == "fallback"


def test_existing_real_album_is_preserved_without_repair():
    from app.logic.local_ai.album_validator import resolve_track_album

    album, source, confidence = resolve_track_album(
        track={"title": "Song", "artist": "Artist", "album": "Hybrid Theory"},
        model_album="Singles",
        genre="Rock",
    )

    assert album == "Hybrid Theory"
    assert source == "existing"
    assert confidence == 1.0


def test_album_cannot_equal_full_song_title():
    from app.logic.local_ai.album_validator import validate_album_suggestion

    album, _ = validate_album_suggestion(
        "Nightcore - Hate Me",
        track={"title": "Nightcore - Hate Me", "artist": "Artist"},
        genre="Electronic",
    )

    assert album != "Nightcore - Hate Me"


def test_album_cannot_equal_artist_name():
    from app.logic.local_ai.album_validator import validate_album_suggestion

    album, _ = validate_album_suggestion(
        "Avril Lavigne",
        track={"title": "Complicated", "artist": "Avril Lavigne"},
        genre="Pop",
    )

    assert album != "Avril Lavigne"


def test_album_sanitizer_rejects_path_traversal_chars():
    from app.logic.local_ai.album_validator import sanitize_album_name

    assert "/" not in sanitize_album_name("Bad/Album")
    assert "\\" not in sanitize_album_name("Bad\\Album")
    assert ".." not in sanitize_album_name("../Escape")
    assert ":" not in sanitize_album_name("Bad:Album")


def test_same_input_classified_twice_gives_same_album():
    from app.logic.local_ai.album_validator import resolve_track_album

    track = {"title": "Nightcore - Living Life, In The Night (Lyrics)", "artist": "Artist", "album": ""}
    first = resolve_track_album(track=track, genre="Electronic", style="Nightcore", tags=["Nightcore", "Lyrics"])
    second = resolve_track_album(track=track, genre="Electronic", style="Nightcore", tags=["Nightcore", "Lyrics"])

    assert first[0] == second[0]


def test_duplicate_tracks_get_same_album():
    from app.logic.local_ai.album_validator import resolve_track_album

    track_a = {"title": "Nightcore - Hate Me", "artist": "Artist", "album": "", "videoId": "abc123xyz01"}
    track_b = {"title": "Nightcore - Hate Me", "artist": "Artist", "album": "", "videoId": "abc123xyz01"}
    assert resolve_track_album(track=track_a, genre="Electronic", style="Nightcore")[0] == resolve_track_album(
        track=track_b, genre="Electronic", style="Nightcore"
    )[0]


def test_write_albums_writes_album_metadata(tmp_path):
    from mutagen.id3 import ID3

    from app.logic.local_ai.enrichment_service import read_audio_file_metadata, write_audio_metadata

    audio_path = tmp_path / "song.mp3"
    audio_path.write_bytes(b"fake audio")
    ID3().save(str(audio_path), v2_version=3)

    write_audio_metadata(
        str(audio_path),
        {"album": "Nightcore Collection", "genre": "Electronic", "tags": [], "videoId": ""},
        write_album=True,
        write_tags=True,
    )

    meta = read_audio_file_metadata(str(audio_path))
    assert meta["album"] == "Nightcore Collection"


def test_move_files_dry_run_shows_plan_without_moving(tmp_path):
    from app.logic.local_ai.enrichment_service import move_track_to_album_folder

    lib = tmp_path / "music"
    unknown_album = lib / "Artist" / "Unknown Album"
    unknown_album.mkdir(parents=True)
    song = unknown_album / "01 - Song.mp3"
    song.write_bytes(b"fake")

    plan = move_track_to_album_folder(
        path=str(song),
        artist="Artist",
        target_album="Nightcore Collection",
        music_dir=str(lib),
        dry_run=True,
    )

    assert plan is not None
    assert plan["album"] == "Nightcore Collection"
    assert song.exists()
    assert not (lib / "Artist" / "Nightcore Collection" / "01 - Song.mp3").exists()


def test_move_files_moves_from_unknown_album_safely(tmp_path):
    from app.logic.local_ai.enrichment_service import move_track_to_album_folder

    lib = tmp_path / "music"
    unknown_album = lib / "Artist" / "Unknown Album"
    unknown_album.mkdir(parents=True)
    song = unknown_album / "01 - Song.mp3"
    song.write_bytes(b"fake")

    result = move_track_to_album_folder(
        path=str(song),
        artist="Artist",
        target_album="Nightcore Collection",
        music_dir=str(lib),
        dry_run=False,
    )

    assert result is not None
    destination = lib / "Artist" / "Nightcore Collection" / "01 - Song.mp3"
    assert destination.exists()
    assert not song.exists()
    assert not unknown_album.exists()


def test_ollama_merge_sets_album_from_model(monkeypatch):
    from app.logic.local_ai.ollama_classifier import OllamaClassifier

    monkeypatch.setattr(
        OllamaClassifier,
        "_call_ollama",
        lambda self, prompt: json.dumps(
            {
                "genre": "Electronic",
                "primary_genre": "Electronic",
                "style": "Nightcore",
                "subgenre": None,
                "collection": None,
                "album": "Nightcore Collection",
                "tags": ["Nightcore"],
                "mood": [],
                "metadata_quality": "medium",
                "classification_confidence": 0.8,
                "reason": "Nightcore remix.",
            }
        ),
    )

    result = OllamaClassifier(base_url="http://localhost:11434", model="test-model").classify(
        {"title": "Nightcore - Hate Me", "artist": "Artist", "album": "Unknown Album", "genre": ""}
    )

    assert result["album"] == "Nightcore Collection"
    assert result["album_source"] == "local_ai"
    assert result["album_confidence"] > 0
