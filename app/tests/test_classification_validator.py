from __future__ import annotations

import json

import pytest


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
    assert "Anime" in result["tags"]
    assert "Op" in result["tags"] or "OP" in result["tags"] or "op" in [t.lower() for t in result["tags"]]
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


def test_validator_lowers_confidence_for_hip_hop_jumpstyle_mismatch():
    from app.logic.local_ai.classification_validator import validate_model_classification

    result = validate_model_classification(
        {
            "genre": "Hip Hop",
            "primary_genre": "Hip Hop",
            "style": "Jumpstyle",
            "subgenre": None,
            "collection": None,
            "tags": ["jumpstyle", "nightcore"],
            "mood": [],
            "metadata_quality": "low",
            "classification_confidence": 0.9,
            "reason": "Tagged as hip hop.",
        }
    )

    assert result["primary_genre"] == "Hip Hop"
    assert result["classification_confidence"] <= 0.45
    assert "jumpstyle" in result["reason"].lower()


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
    assert "Anime" in result["tags"]


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
        }
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
    assert "Game" in result["tags"]
    assert "Ost" in result["tags"] or "OST" in result["tags"]


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
