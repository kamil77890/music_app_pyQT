from __future__ import annotations

import json


def test_validator_moves_anime_genre_to_tags_and_soundtrack_for_ost():
    from app.logic.local_ai.classification_validator import validate_model_classification

    track = {"title": "Tokyo Ghoul OP - Unravel [Piano]", "artist": "Artist"}
    result = validate_model_classification(
        {
            "genre": "Anime",
            "primary_genre": "Anime",
            "style": "Piano",
            "subgenre": "OP",
            "collection": None,
            "tags": ["OST"],
            "mood": [],
            "metadata_quality": "medium",
            "classification_confidence": 0.9,
            "reason": "Anime opening theme.",
        },
        track=track,
    )

    assert result["primary_genre"] == "Soundtrack"
    assert result["genre"] == "Soundtrack"
    assert result["style"] == "Piano"


def test_validator_moves_cyberpunk_genre_to_collection_and_tags():
    from app.logic.local_ai.classification_validator import validate_model_classification

    result = validate_model_classification(
        {
            "genre": "Cyberpunk",
            "primary_genre": "Cyberpunk",
            "style": "Piano",
            "subgenre": None,
            "collection": None,
            "tags": ["OST"],
            "mood": [],
            "metadata_quality": "medium",
            "classification_confidence": 0.8,
            "reason": "Cyberpunk franchise piano cover.",
        },
        track={"title": "Cyberpunk Edgerunners Piano Version", "artist": "Artist"},
    )

    assert result["primary_genre"] == "Soundtrack"
    assert result["genre"] == "Soundtrack"
    assert result["collection"] == "Cyberpunk"
    assert "Cyberpunk" in result["tags"]
    assert result["style"] == "Piano"


def test_validator_jumpstyle_consistency_sets_dance():
    from app.logic.local_ai.classification_validator import validate_model_classification

    result = validate_model_classification(
        {
            "genre": "Unknown Genre",
            "primary_genre": "Unknown Genre",
            "style": "Nightcore",
            "subgenre": None,
            "collection": None,
            "tags": ["Jumpstyle", "Nightcore"],
            "mood": [],
            "metadata_quality": "low",
            "classification_confidence": 0.9,
            "reason": "Nightcore jumpstyle track.",
        },
        track={"title": "Nightcore - HEAVENLY JUMPSTYLE (Lyrics)", "artist": "Artist"},
    )

    assert result["primary_genre"] in {"Dance", "Electronic"}
    assert result["style"] == "Nightcore"
    assert "Jumpstyle" in result["tags"]


def test_validator_rejects_garbage_id_genre():
    from app.logic.local_ai.classification_validator import validate_model_classification

    result = validate_model_classification(
        {
            "genre": "pzXMXGM21YI",
            "primary_genre": "pzXMXGM21YI",
            "style": None,
            "subgenre": None,
            "collection": None,
            "tags": [],
            "mood": [],
            "metadata_quality": "low",
            "classification_confidence": 0.5,
            "reason": "test",
        }
    )

    assert result["genre"] == "Unknown Genre"
    assert result["primary_genre"] == "Unknown Genre"


def test_ollama_classifier_applies_validator_to_mock_response(monkeypatch):
    from app.logic.local_ai.ollama_classifier import OllamaClassifier

    monkeypatch.setattr(
        OllamaClassifier,
        "_call_ollama",
        lambda self, prompt: json.dumps(
            {
                "genre": "Anime",
                "primary_genre": "Anime",
                "style": "Piano",
                "subgenre": "OP",
                "collection": None,
                "tags": ["opening"],
                "mood": ["emotional"],
                "metadata_quality": "medium",
                "classification_confidence": 0.88,
                "reason": "Anime opening piano arrangement.",
            }
        ),
    )

    result = OllamaClassifier(base_url="http://localhost:11434", model="test-model").classify(
        {"title": "Show OP Piano", "artist": "Artist", "genre": ""}
    )

    assert result["metadata_source"] == "local_ai"
    assert result["primary_genre"] == "Soundtrack"


def test_validator_filters_weak_tags_and_normalizes_versions():
    from app.logic.local_ai.classification_validator import validate_model_classification

    result = validate_model_classification(
        {
            "genre": "Rock",
            "primary_genre": "Rock",
            "style": None,
            "subgenre": None,
            "collection": None,
            "tags": ["Rock Version", "Harder", "Different", "Lyrics"],
            "mood": [],
            "metadata_quality": "medium",
            "classification_confidence": 0.9,
            "reason": "Rock version with lyrics.",
        },
        track={"title": "Rock Version with Lyrics", "artist": "Artist"},
    )

    assert "Rock" in result["tags"]
    assert "Lyrics" in result["tags"]
    assert "Harder" not in result["tags"]
    assert "Different" not in result["tags"]
    assert "Version" not in result["tags"]


def test_validator_coerces_list_like_style_and_collection_strings():
    from app.logic.local_ai.classification_validator import validate_model_classification

    result = validate_model_classification(
        {
            "genre": "Soundtrack",
            "primary_genre": "Soundtrack",
            "style": "['Piano']",
            "subgenre": None,
            "collection": "['Anime', 'Game', 'OST']",
            "tags": [],
            "mood": [],
            "metadata_quality": "medium",
            "classification_confidence": 0.7,
            "reason": "Game anime OST piano version.",
        },
        track={"title": "Episode 6 OST Piano", "artist": "Artist"},
    )

    assert result["style"] == "Piano"
    assert result["collection"] == "Anime"
    assert "Ost" in result["tags"] or "OST" in result["tags"]
    assert "Game" not in result["tags"]


def test_validator_sanitizes_unsupported_reason_claims():
    from app.logic.local_ai.classification_validator import validate_model_classification

    result = validate_model_classification(
        {
            "genre": "Soundtrack",
            "primary_genre": "Soundtrack",
            "style": "Piano",
            "subgenre": None,
            "collection": "Cyberpunk",
            "tags": ["OST"],
            "mood": [],
            "metadata_quality": "medium",
            "classification_confidence": 0.7,
            "reason": "Cyberpunk Edgerunners is a manga series with piano covers.",
        },
        track={"title": "Cyberpunk Edgerunners Piano Version", "artist": "Artist"},
    )

    assert "manga" not in result["reason"].lower()


def test_validator_removes_artist_name_from_tags():
    from app.logic.local_ai.classification_validator import validate_model_classification

    result = validate_model_classification(
        {
            "genre": "Soundtrack",
            "primary_genre": "Soundtrack",
            "style": "Piano",
            "subgenre": None,
            "collection": None,
            "tags": ["Luminote", "Piano"],
            "mood": [],
            "metadata_quality": "medium",
            "classification_confidence": 0.9,
            "reason": "Piano cover.",
        },
        track={"title": "OP Piano", "artist": "Luminote"},
    )

    assert "Luminote" not in result["tags"]
    assert "Piano" in result["tags"]


def test_validator_removes_song_title_word_leakage_from_tags():
    from app.logic.local_ai.classification_validator import validate_model_classification

    result = validate_model_classification(
        {
            "genre": "Electronic",
            "primary_genre": "Electronic",
            "style": "Nightcore",
            "subgenre": None,
            "collection": None,
            "tags": ["Young", "Nightcore", "Punk"],
            "mood": [],
            "metadata_quality": "low",
            "classification_confidence": 0.9,
            "reason": "Nightcore remix.",
        },
        track={"title": "Nightcore - Die Young", "artist": "Artist"},
    )

    assert "Young" not in result["tags"]
    assert "Punk" not in result["tags"]
    assert "Nightcore" in result["tags"]


def test_validator_removes_useless_adjective_tags():
    from app.logic.local_ai.classification_validator import validate_model_classification

    result = validate_model_classification(
        {
            "genre": "Dance",
            "primary_genre": "Dance",
            "style": "Nightcore",
            "subgenre": None,
            "collection": None,
            "tags": ["Harder", "Different", "Nightcore", "Jumpstyle"],
            "mood": [],
            "metadata_quality": "low",
            "classification_confidence": 0.9,
            "reason": "Nightcore jumpstyle.",
        },
        track={"title": "Nightcore - HEAVENLY JUMPSTYLE", "artist": "Artist"},
    )

    assert "Harder" not in result["tags"]
    assert "Different" not in result["tags"]
    assert "Nightcore" in result["tags"]
    assert "Jumpstyle" in result["tags"]


def test_validator_rock_version_sets_rock_genre():
    from app.logic.local_ai.classification_validator import validate_model_classification

    result = validate_model_classification(
        {
            "genre": "Unknown Genre",
            "primary_genre": "Unknown Genre",
            "style": "Nightcore",
            "subgenre": None,
            "collection": None,
            "tags": ["Rock Version", "Lyrics"],
            "mood": [],
            "metadata_quality": "medium",
            "classification_confidence": 0.9,
            "reason": "Rock version nightcore.",
        },
        track={"title": "Nightcore - Poker Face (Rock Version) (Lyrics)", "artist": "Artist"},
    )

    assert result["genre"] == "Rock"
    assert result["primary_genre"] == "Rock"
    assert "Rock" in result["tags"]
    assert "Nightcore" in result["tags"]
    assert "Lyrics" in result["tags"]
    assert "Rock Version" not in result["tags"]


def test_validator_removes_unsupported_game_tag():
    from app.logic.local_ai.classification_validator import validate_model_classification

    result = validate_model_classification(
        {
            "genre": "Soundtrack",
            "primary_genre": "Soundtrack",
            "style": "Piano",
            "subgenre": None,
            "collection": None,
            "tags": ["Game", "Piano", "OST"],
            "mood": [],
            "metadata_quality": "medium",
            "classification_confidence": 0.8,
            "reason": "Piano soundtrack.",
        },
        track={"title": "Cyberpunk Piano Version", "artist": "Artist"},
    )

    assert "Game" not in result["tags"]
    assert "Piano" in result["tags"]


def test_validator_piano_ost_sets_soundtrack():
    from app.logic.local_ai.classification_validator import validate_model_classification

    result = validate_model_classification(
        {
            "genre": "Unknown Genre",
            "primary_genre": "Unknown Genre",
            "style": "Piano",
            "subgenre": None,
            "collection": None,
            "tags": ["OST"],
            "mood": [],
            "metadata_quality": "medium",
            "classification_confidence": 0.9,
            "reason": "Piano OST.",
        },
        track={"title": "Episode 6 OST Piano", "artist": "Artist"},
    )

    assert result["genre"] == "Soundtrack"
    assert result["style"] == "Piano"


def test_validator_anime_not_main_genre():
    from app.logic.local_ai.classification_validator import validate_model_classification

    result = validate_model_classification(
        {
            "genre": "Anime",
            "primary_genre": "Anime",
            "style": "Piano",
            "subgenre": None,
            "collection": None,
            "tags": [],
            "mood": [],
            "metadata_quality": "medium",
            "classification_confidence": 0.9,
            "reason": "Anime piano.",
        },
        track={"title": "OP Piano", "artist": "Artist"},
    )

    assert result["genre"] not in {"Anime", "Cyberpunk"}
    assert result["primary_genre"] not in {"Anime", "Cyberpunk"}


def test_validator_unknown_genre_confidence_not_high():
    from app.logic.local_ai.classification_validator import validate_model_classification

    result = validate_model_classification(
        {
            "genre": "Unknown Genre",
            "primary_genre": "Unknown Genre",
            "style": "Nightcore",
            "subgenre": None,
            "collection": None,
            "tags": ["Nightcore"],
            "mood": [],
            "metadata_quality": "low",
            "classification_confidence": 0.95,
            "reason": "Uncertain.",
        }
    )

    assert result["classification_confidence"] <= 0.45


def test_validator_reason_max_length():
    from app.logic.local_ai.classification_validator import validate_model_classification

    long_reason = "x" * 200
    result = validate_model_classification(
        {
            "genre": "Rock",
            "primary_genre": "Rock",
            "style": None,
            "subgenre": None,
            "collection": None,
            "tags": ["Rock"],
            "mood": [],
            "metadata_quality": "medium",
            "classification_confidence": 0.8,
            "reason": long_reason,
        }
    )

    assert len(result["reason"]) <= 160


def test_validator_maps_electro_pop_to_electronic():
    from app.logic.local_ai.classification_validator import validate_model_classification

    result = validate_model_classification(
        {
            "genre": "Electro Pop",
            "primary_genre": "Electro Pop",
            "style": "Piano",
            "subgenre": None,
            "collection": None,
            "tags": ["Piano"],
            "mood": [],
            "metadata_quality": "medium",
            "classification_confidence": 0.85,
            "reason": "Electro pop piano.",
        },
        track={"title": "Electro Pop Piano Mix", "artist": "Artist"},
    )

    assert result["primary_genre"] == "Electronic"
    assert result["genre"] == "Electronic"


def test_validator_die_young_rejects_ungrounded_piano_and_jumpstyle():
    from app.logic.local_ai.classification_validator import validate_model_classification

    track = {"title": "Nightcore - Die Young", "artist": "Artist"}
    payload = {
        "genre": "Electronic",
        "primary_genre": "Electronic",
        "style": "Nightcore",
        "subgenre": None,
        "collection": None,
        "tags": ["Piano", "Jumpstyle", "Nightcore"],
        "mood": [],
        "metadata_quality": "low",
        "classification_confidence": 0.9,
        "reason": "Nightcore remix.",
    }
    result = validate_model_classification(payload, track=track)

    assert "Piano" not in result["tags"]
    assert "Jumpstyle" not in result["tags"]
    assert "Nightcore" in result["tags"]


def test_validator_die_young_keeps_jumpstyle_only_with_input():
    from app.logic.local_ai.classification_validator import validate_model_classification

    without = validate_model_classification(
        {
            "genre": "Dance",
            "primary_genre": "Dance",
            "style": "Nightcore",
            "subgenre": None,
            "collection": None,
            "tags": ["Jumpstyle", "Nightcore"],
            "mood": [],
            "metadata_quality": "low",
            "classification_confidence": 0.9,
            "reason": "Nightcore remix.",
        },
        track={"title": "Nightcore - Die Young", "artist": "Artist"},
    )
    with_jumpstyle = validate_model_classification(
        {
            "genre": "Dance",
            "primary_genre": "Dance",
            "style": "Nightcore",
            "subgenre": None,
            "collection": None,
            "tags": ["Jumpstyle", "Nightcore"],
            "mood": [],
            "metadata_quality": "low",
            "classification_confidence": 0.9,
            "reason": "Nightcore jumpstyle remix.",
        },
        track={"title": "Nightcore - Die Young (Jumpstyle)", "artist": "Artist"},
    )

    assert "Jumpstyle" not in without["tags"]
    assert "Jumpstyle" in with_jumpstyle["tags"]


def test_validator_ost_piano_rejects_ungrounded_lyrics():
    from app.logic.local_ai.classification_validator import validate_model_classification

    payload = {
        "genre": "Soundtrack",
        "primary_genre": "Soundtrack",
        "style": "Piano",
        "subgenre": None,
        "collection": None,
        "tags": ["Lyrics", "Piano", "OST"],
        "mood": [],
        "metadata_quality": "medium",
        "classification_confidence": 0.9,
        "reason": "OST piano cover.",
    }
    solo = validate_model_classification(payload, track={"title": "Solo Leveling OST Piano", "artist": "Artist"})
    tokyo = validate_model_classification(payload, track={"title": "Tokyo Ghoul OP Piano", "artist": "Artist"})

    assert "Lyrics" not in solo["tags"]
    assert "Lyrics" not in tokyo["tags"]
    assert "Piano" in solo["tags"]
    assert "Piano" in tokyo["tags"]


def test_validator_piano_version_keeps_piano_style_and_tag():
    from app.logic.local_ai.classification_validator import validate_model_classification

    result = validate_model_classification(
        {
            "genre": "Unknown Genre",
            "primary_genre": "Unknown Genre",
            "style": "Piano",
            "subgenre": None,
            "collection": None,
            "tags": ["Piano"],
            "mood": [],
            "metadata_quality": "medium",
            "classification_confidence": 0.9,
            "reason": "Piano version.",
        },
        track={"title": "Song Piano Version", "artist": "Artist"},
    )

    assert result["style"] == "Piano"
    assert "Piano" in result["tags"]


def test_validator_same_payload_twice_returns_same_result():
    from app.logic.local_ai.classification_validator import validate_model_classification

    track = {"title": "Nightcore - Poker Face (Rock Version) (Lyrics)", "artist": "Artist"}
    payload = {
        "genre": "Rock",
        "primary_genre": "Rock",
        "style": "Nightcore",
        "subgenre": None,
        "collection": None,
        "tags": ["Rock", "Nightcore", "Lyrics", "Piano"],
        "mood": [],
        "metadata_quality": "medium",
        "classification_confidence": 0.9,
        "reason": "Rock version nightcore with lyrics.",
    }
    first = validate_model_classification(payload, track=track)
    second = validate_model_classification(payload, track=track)

    assert first == second


def test_validator_avril_complicated_rejects_piano():
    from app.logic.local_ai.classification_validator import validate_model_classification

    result = validate_model_classification(
        {
            "genre": "Pop",
            "primary_genre": "Pop",
            "style": "Piano",
            "subgenre": None,
            "collection": None,
            "tags": ["Piano", "Pop"],
            "mood": [],
            "metadata_quality": "medium",
            "classification_confidence": 0.9,
            "reason": "Pop piano cover.",
        },
        track={"title": "Avril Lavigne - Complicated (Official Video)", "artist": "Avril Lavigne"},
    )

    assert "Piano" not in result["tags"]
    assert result["style"] is None
    assert result["genre"] == "Pop"


def test_validator_skars_massacre_rejects_piano():
    from app.logic.local_ai.classification_validator import validate_model_classification

    result = validate_model_classification(
        {
            "genre": "Unknown Genre",
            "primary_genre": "Unknown Genre",
            "style": "Piano",
            "subgenre": None,
            "collection": None,
            "tags": ["Piano"],
            "mood": [],
            "metadata_quality": "low",
            "classification_confidence": 0.9,
            "reason": "Animated music video.",
        },
        track={"title": "SKARS - Massacre (Animated Music Video)", "artist": "SKARS"},
    )

    assert "Piano" not in result["tags"]
    assert result["style"] is None


def test_validator_linkin_park_from_the_inside_rejects_instrumental():
    from app.logic.local_ai.classification_validator import validate_model_classification

    result = validate_model_classification(
        {
            "genre": "Rock",
            "primary_genre": "Rock",
            "style": "Instrumental",
            "subgenre": None,
            "collection": None,
            "tags": ["Instrumental"],
            "mood": [],
            "metadata_quality": "medium",
            "classification_confidence": 0.9,
            "reason": "Rock track.",
        },
        track={
            "title": "From The Inside (Official Music Video) [4K UPGRADE] – Linkin Park",
            "artist": "Linkin Park",
        },
    )

    assert "Instrumental" not in result["tags"]
    assert result["style"] is None


def test_validator_middle_of_the_night_anime_mix_rejects_nightcore():
    from app.logic.local_ai.classification_validator import validate_model_classification

    result = validate_model_classification(
        {
            "genre": "Electronic",
            "primary_genre": "Electronic",
            "style": "Nightcore",
            "subgenre": None,
            "collection": None,
            "tags": ["Nightcore"],
            "mood": [],
            "metadata_quality": "medium",
            "classification_confidence": 0.9,
            "reason": "Anime mix.",
        },
        track={"title": "Middle of the Night「AMV」Anime Mix", "artist": "Artist"},
    )

    assert "Nightcore" not in result["tags"]
    assert result["style"] is None


def test_validator_existing_file_piano_tag_is_not_proof():
    from app.logic.local_ai.classification_validator import validate_model_classification

    result = validate_model_classification(
        {
            "genre": "Pop",
            "primary_genre": "Pop",
            "style": None,
            "subgenre": None,
            "collection": None,
            "tags": ["Piano", "Pop"],
            "mood": [],
            "metadata_quality": "medium",
            "classification_confidence": 0.9,
            "reason": "Pop track.",
        },
        track={
            "title": "Avril Lavigne - Complicated (Official Video)",
            "artist": "Avril Lavigne",
            "file_tags": ["Piano"],
            "genre": "Piano",
        },
    )

    assert "Piano" not in result["tags"]


def test_write_audio_metadata_replaces_managed_tags(tmp_path):
    from mutagen.id3 import ID3, TCON, TXXX

    from app.logic.local_ai.enrichment_service import read_audio_file_metadata, write_audio_metadata

    audio_path = tmp_path / "song.mp3"
    audio_path.write_bytes(b"fake audio")
    tags = ID3()
    tags.add(TCON(encoding=3, text="Piano"))
    tags.add(TXXX(encoding=3, desc="LOCAL_AI_TAGS", text='["Piano", "Instrumental"]'))
    tags.save(str(audio_path), v2_version=3)

    write_audio_metadata(
        str(audio_path),
        {
            "genre": "Pop",
            "tags": ["Pop"],
            "videoId": "",
        },
    )

    repaired = ID3(str(audio_path))
    assert str(repaired["TCON"].text[0]) == "Pop"
    assert read_audio_file_metadata(str(audio_path))["managed_tags"] == ["Pop"]
