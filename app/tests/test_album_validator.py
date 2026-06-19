from __future__ import annotations

import json


def _resolve(track: dict, **kwargs):
    from app.logic.local_ai.album_validator import resolve_track_album_metadata

    result = resolve_track_album_metadata(track=track, **kwargs)
    return result.album, result.collection, result.album_source, result.album_confidence


def test_unknown_album_nightcore_title_gets_singles_and_nightcore_collection():
    album, collection, source, confidence = _resolve(
        {"title": "Nightcore - Hate Me", "artist": "Artist", "album": "Unknown Album"},
        genre="Electronic",
        style="Nightcore",
        tags=["Nightcore"],
    )

    assert album == "Singles"
    assert collection == "Nightcore Collection"
    assert source in {"fallback", "local_ai"}
    assert confidence > 0


def test_unknown_album_official_music_video_gets_singles_and_music_videos():
    album, collection, _, _ = _resolve(
        {"title": "Avril Lavigne - Complicated (Official Music Video)", "artist": "Avril Lavigne", "album": ""},
        genre="Pop",
    )

    assert album == "Singles"
    assert collection == "Music Videos"


def test_unknown_album_anime_mv_gets_singles_and_anime_soundtracks():
    album, collection, _, _ = _resolve(
        {"title": "Tokyo Ghoul OP - Unravel [Piano/Animenz arr.]", "artist": "Luminote", "album": "Unknown Album"},
        genre="Soundtrack",
        style="Piano",
        tags=["OST", "Piano"],
    )

    assert album == "Singles"
    assert collection == "Anime Soundtracks"


def test_unknown_album_piano_version_gets_singles_and_piano_versions():
    album, collection, _, _ = _resolve(
        {"title": "Song Piano Version", "artist": "Artist", "album": "Unknown Album"},
        genre="Unknown Genre",
        style="Piano",
    )

    assert album == "Singles"
    assert collection == "Piano Versions"


def test_unknown_album_ost_piano_gets_singles_and_ost_collection():
    album, collection, _, _ = _resolve(
        {"title": "Solo Leveling Episode 6 OST Piano", "artist": "Artist", "album": ""},
        genre="Soundtrack",
        style="Piano",
        tags=["OST"],
    )

    assert album == "Singles"
    assert collection in {"OST Collection", "Anime Soundtracks"}


def test_live_track_gets_live_recordings_album():
    album, collection, _, _ = _resolve(
        {"title": "Song (Live at Wembley)", "artist": "Artist", "album": "Unknown Album"},
        genre="Rock",
        style="Live",
        tags=["Live"],
    )

    assert album == "Live Recordings"
    assert collection == "Live Recordings"


def test_fake_album_nightcore_collection_gets_repaired_to_singles():
    album, collection, source, _ = _resolve(
        {"title": "Nightcore - Take A Hint (Lyrics)", "artist": "Kenke", "album": "Nightcore Collection"},
        genre="Electronic",
        style="Nightcore",
        tags=["Nightcore"],
        repair_managed_albums=True,
    )

    assert album == "Singles"
    assert collection == "Nightcore Collection"
    assert source in {"fallback", "local_ai"}


def test_fake_album_music_videos_gets_repaired_to_singles():
    album, collection, _, _ = _resolve(
        {"title": "Avril Lavigne - Complicated (Official Video)", "artist": "Avril Lavigne", "album": "Music Videos"},
        genre="Pop",
        repair_managed_albums=True,
    )

    assert album == "Singles"
    assert collection == "Music Videos"


def test_fake_album_anime_soundtracks_gets_repaired_to_singles():
    album, collection, _, _ = _resolve(
        {"title": "Tokyo Ghoul OP - Unravel", "artist": "Luminote", "album": "Anime Soundtracks"},
        genre="Soundtrack",
        repair_managed_albums=True,
    )

    assert album == "Singles"
    assert collection == "Anime Soundtracks"


def test_move_files_dry_run_repair_plans_move_from_fake_folder_to_singles(tmp_path):
    from app.logic.local_ai.enrichment_service import move_track_to_album_folder

    lib = tmp_path / "music"
    fake_album = lib / "Kenke" / "Nightcore Collection"
    fake_album.mkdir(parents=True)
    song = fake_album / "00 - Nightcore - Take A Hint.mp3"
    song.write_bytes(b"fake")

    plan = move_track_to_album_folder(
        path=str(song),
        artist="Kenke",
        target_album="Singles",
        music_dir=str(lib),
        dry_run=True,
    )

    assert plan is not None
    assert plan["album"] == "Singles"
    assert plan["from"].endswith("Nightcore Collection/00 - Nightcore - Take A Hint.mp3")
    assert plan["to"].endswith("Singles/00 - Nightcore - Take A Hint.mp3")
    assert song.exists()


def test_move_files_repair_moves_from_fake_folder_to_singles_safely(tmp_path):
    from app.logic.local_ai.enrichment_service import move_track_to_album_folder

    lib = tmp_path / "music"
    fake_album = lib / "Luminote" / "Anime Soundtracks"
    fake_album.mkdir(parents=True)
    song = fake_album / "01 - Unravel.mp3"
    song.write_bytes(b"fake")

    result = move_track_to_album_folder(
        path=str(song),
        artist="Luminote",
        target_album="Singles",
        music_dir=str(lib),
        dry_run=False,
    )

    assert result is not None
    destination = lib / "Luminote" / "Singles" / "01 - Unravel.mp3"
    assert destination.exists()
    assert not song.exists()
    assert not fake_album.exists()


def test_existing_real_album_is_preserved():
    album, collection, source, confidence = _resolve(
        {"title": "Song", "artist": "Artist", "album": "Hybrid Theory"},
        model_album="Singles",
        genre="Rock",
    )

    assert album == "Hybrid Theory"
    assert source == "existing"
    assert confidence == 1.0


def test_same_input_gives_same_album_and_collection():
    track = {"title": "Nightcore - Living Life, In The Night (Lyrics)", "artist": "Artist", "album": ""}
    first = _resolve(track=track, genre="Electronic", style="Nightcore", tags=["Nightcore", "Lyrics"])
    second = _resolve(track=track, genre="Electronic", style="Nightcore", tags=["Nightcore", "Lyrics"])

    assert first[0] == second[0]
    assert first[1] == second[1]


def test_album_cannot_equal_full_song_title():
    from app.logic.local_ai.album_validator import validate_album_suggestion

    album, collection, _ = validate_album_suggestion(
        "Nightcore - Hate Me",
        track={"title": "Nightcore - Hate Me", "artist": "Artist"},
        genre="Electronic",
    )

    assert album != "Nightcore - Hate Me"
    assert album == "Singles"
    assert collection == "Nightcore Collection"


def test_album_cannot_equal_artist_name():
    from app.logic.local_ai.album_validator import validate_album_suggestion

    album, _, _ = validate_album_suggestion(
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


def test_write_albums_writes_album_and_collection_metadata(tmp_path):
    from mutagen.id3 import ID3

    from app.logic.local_ai.enrichment_service import read_audio_file_metadata, write_audio_metadata

    audio_path = tmp_path / "song.mp3"
    audio_path.write_bytes(b"fake audio")
    ID3().save(str(audio_path), v2_version=3)

    write_audio_metadata(
        str(audio_path),
        {
            "album": "Singles",
            "collection": "Nightcore Collection",
            "genre": "Electronic",
            "tags": [],
            "videoId": "",
        },
        write_album=True,
        write_tags=True,
    )

    meta = read_audio_file_metadata(str(audio_path))
    assert meta["album"] == "Singles"
    assert meta["managed_collection"] == "Nightcore Collection"


def test_ollama_merge_maps_fake_model_album_to_singles_and_collection(monkeypatch):
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

    assert result["album"] == "Singles"
    assert result["collection"] == "Nightcore Collection"
    assert result["album_source"] in {"local_ai", "fallback"}
    assert result["album_confidence"] > 0
