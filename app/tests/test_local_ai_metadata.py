from pathlib import Path
import json


FORBIDDEN_HARDCODED_STRINGS = [
    "Tokyo Ghoul",
    "Solo Leveling",
    "Nightcore Rock",
    "Cyberpunk OST",
    "Grim Cat Piano",
    "Luminote",
    "Attack on Titan",
    "Demon Slayer",
]


def test_video_id_in_tcon_is_garbage_genre():
    from app.logic.local_ai.metadata_normalizer import is_garbage_genre, normalize_genre

    assert is_garbage_genre("pzXMXGM21YI") is True
    assert normalize_genre("pzXMXGM21YI") == "Unknown Genre"


def test_garbage_genre_falls_back_to_unknown_genre():
    from app.logic.local_ai.metadata_normalizer import normalize_genre

    assert normalize_genre("") == "Unknown Genre"
    assert normalize_genre("a94f8a4f3d2e9c2b1a0d9f8e7c6b5a4f") == "Unknown Genre"
    assert normalize_genre("QwErTy12345") == "Unknown Genre"


def test_normal_genre_is_preserved_and_normalized():
    from app.logic.local_ai.metadata_normalizer import normalize_genre

    assert normalize_genre("hip hop") == "Hip Hop"
    assert normalize_genre("Electronic") == "Electronic"


def test_unknown_album_fallback_is_stable():
    from app.logic.local_ai.metadata_normalizer import normalize_album

    assert normalize_album("") == "Unknown Album"
    assert normalize_album("N/A") == "Unknown Album"
    assert normalize_album("  My Album  ") == "My Album"


def test_metadata_quality_low_medium_high():
    from app.logic.local_ai.metadata_normalizer import calculate_metadata_quality

    assert calculate_metadata_quality({"title": "", "artist": "", "album": "", "genre": ""}) == "low"
    assert calculate_metadata_quality({"title": "Song", "artist": "Artist", "album": "", "genre": ""}) == "medium"
    assert calculate_metadata_quality({"title": "Song", "artist": "Artist", "album": "Album", "genre": "Rock"}) == "high"


def test_local_ai_disabled_does_not_crash(monkeypatch):
    from app.logic.local_ai.enrichment_service import enrich_track_metadata

    monkeypatch.setenv("LOCAL_AI_METADATA_ENABLED", "false")

    enriched = enrich_track_metadata({"title": "lofi night drive", "artist": "Unknown Artist", "genre": "pzXMXGM21YI"})

    assert enriched["genre"] == "Unknown Genre"
    assert enriched["primary_genre"] == "Unknown Genre"
    assert enriched["metadata_source"] == "fallback"
    assert enriched["tags"] == []
    assert enriched["mood"] == []


def test_enrichment_moves_legacy_video_id_genre_to_video_id():
    from app.logic.local_ai.enrichment_service import enrich_track_metadata

    enriched = enrich_track_metadata({"title": "Song", "artist": "Artist", "genre": "pzXMXGM21YI"})

    assert enriched["genre"] == "Unknown Genre"
    assert enriched["videoId"] == "pzXMXGM21YI"


def test_fallback_classifier_does_not_guess_genre_from_title():
    from app.logic.local_ai.fallback_classifier import FallbackClassifier

    classifier = FallbackClassifier()
    result = classifier.classify(
        {
            "title": "Tokyo Ghoul OP - Unravel [Piano]",
            "artist": "Luminote",
            "genre": "",
        }
    )

    assert result["genre"] == "Unknown Genre"
    assert result["primary_genre"] == "Unknown Genre"
    assert result["style"] is None
    assert result["subgenre"] is None
    assert result["tags"] == []
    assert result["mood"] == []
    assert result["metadata_source"] == "fallback"
    assert result["classification_confidence"] == 0.0


def test_fallback_classifier_preserves_existing_clean_genre():
    from app.logic.local_ai.fallback_classifier import FallbackClassifier

    result = FallbackClassifier().classify({"title": "Song", "artist": "Artist", "genre": "Rock"})

    assert result["genre"] == "Rock"
    assert result["primary_genre"] == "Rock"
    assert result["classification_confidence"] == 0.2


def test_ollama_classifier_uses_model_response(monkeypatch):
    from app.logic.local_ai.ollama_classifier import OllamaClassifier

    model_response = {
        "response": json.dumps(
            {
                "genre": "Classical",
                "primary_genre": "Classical",
                "style": "Piano",
                "subgenre": "Solo Piano",
                "mood": ["calm"],
                "tags": ["instrumental"],
                "metadata_quality": "medium",
                "classification_confidence": 0.82,
                "reason": "Piano arrangement inferred from title.",
            }
        )
    }

    monkeypatch.setattr(OllamaClassifier, "_call_ollama", lambda self, prompt: model_response["response"])

    result = OllamaClassifier(base_url="http://localhost:11434", model="test-model").classify(
        {"title": "Moonlight Sonata Piano", "artist": "Artist", "genre": ""}
    )

    assert result["genre"] == "Classical"
    assert result["primary_genre"] == "Classical"
    assert result["style"] == "Piano"
    assert result["subgenre"] == "Solo Piano"
    assert result["mood"] == ["calm"]
    assert "Instrumental" not in result["tags"]
    assert "Piano" in result["tags"]
    assert result["metadata_source"] == "local_ai"
    assert 0.3 <= result["classification_confidence"] <= 0.75


def test_ollama_classifier_falls_back_without_hardcoded_mapping(monkeypatch):
    from app.logic.local_ai.ollama_classifier import OllamaClassifier

    monkeypatch.setattr(OllamaClassifier, "_call_ollama", lambda self, prompt: (_ for _ in ()).throw(RuntimeError("offline")))

    result = OllamaClassifier(base_url="http://localhost:11434", model="test-model").classify(
        {"title": "Nightcore - Poker Face (Rock Version)", "artist": "Nightcore", "genre": ""}
    )

    assert result["genre"] == "Unknown Genre"
    assert result["style"] is None
    assert result["metadata_source"] == "fallback"


def test_garbage_never_becomes_style_or_subgenre():
    from app.logic.local_ai.enrichment_service import enrich_track_metadata

    enriched = enrich_track_metadata({"title": "Song", "artist": "Artist", "genre": "pzXMXGM21YI"})

    assert enriched["genre"] == "Unknown Genre"
    assert enriched["primary_genre"] == "Unknown Genre"
    assert enriched["style"] is None
    assert enriched["subgenre"] is None


def test_enrichment_batch_dry_run_does_not_write_tags(monkeypatch, tmp_path):
    from app.logic.local_ai import enrichment_service
    from app.logic.local_ai.enrichment_service import enrich_library_batch

    track = tmp_path / "song.mp3"
    track.write_bytes(b"fake audio")
    writes = []

    monkeypatch.setenv("LOCAL_AI_CACHE_PATH", str(tmp_path / "cache.json"))
    monkeypatch.setattr(enrichment_service, "scan_music_files", lambda music_dir=None: [{"path": str(track), "title": "lofi song", "artist": "A", "genre": ""}])
    monkeypatch.setattr(enrichment_service, "write_audio_metadata", lambda *args, **kwargs: writes.append(args))

    summary = enrich_library_batch(music_dir=str(tmp_path), dry_run=True, write_tags=False)

    assert summary["analyzed"] == 1
    assert summary["genres_updated"] == 0
    assert writes == []


def test_enrichment_batch_write_tags_writes_cleaned_metadata(monkeypatch, tmp_path):
    from app.logic.local_ai import enrichment_service
    from app.logic.local_ai.enrichment_service import enrich_library_batch

    track = tmp_path / "song.mp3"
    track.write_bytes(b"fake audio")
    writes = []

    monkeypatch.setenv("LOCAL_AI_CACHE_PATH", str(tmp_path / "cache.json"))
    monkeypatch.setattr(
        enrichment_service,
        "scan_music_files",
        lambda music_dir=None: [{"path": str(track), "title": "rock anthem", "artist": "Band", "genre": "Rock", "videoId": "pzXMXGM21YI"}],
    )
    monkeypatch.setattr(enrichment_service, "write_audio_metadata", lambda path, metadata: writes.append((path, metadata)))

    summary = enrich_library_batch(music_dir=str(tmp_path), dry_run=False, write_tags=True)

    assert summary["analyzed"] == 1
    assert writes[0][0] == str(track)
    assert writes[0][1]["genre"] == "Rock"
    assert writes[0][1]["videoId"] == "pzXMXGM21YI"


def test_enrichment_batch_uses_cache_without_reclassifying(monkeypatch, tmp_path):
    from app.logic.local_ai import enrichment_service
    from app.logic.local_ai.classifier_base import CLASSIFIER_VERSION
    from app.logic.local_ai.enrichment_service import enrich_library_batch

    cache_path = tmp_path / "cache.json"
    track = tmp_path / "song.mp3"
    track.write_bytes(b"fake audio")
    song = {"path": str(track), "title": "Song", "artist": "Artist", "genre": "", "fileMtime": 1, "fileSize": 2}
    cache_entry = {
        **song,
        "genre": "Rock",
        "primary_genre": "Rock",
        "style": None,
        "subgenre": None,
        "collection": None,
        "mood": [],
        "tags": ["energetic"],
        "metadata_quality": "high",
        "metadata_source": "local_ai",
        "classification_confidence": 0.8,
        "reason": "cached",
        "_cache_meta": {
            "classifier_version": CLASSIFIER_VERSION,
            "provider": "fallback",
            "model": "",
            "metadata_enabled": False,
            "track_hash": f"{track}|1|2|Song|Artist|",
        },
    }
    cache_path.write_text(json.dumps({f"{track}|1|2": cache_entry}), encoding="utf-8")

    monkeypatch.setenv("LOCAL_AI_CACHE_PATH", str(cache_path))
    monkeypatch.setenv("LOCAL_AI_METADATA_ENABLED", "false")
    monkeypatch.setattr(enrichment_service, "scan_music_files", lambda music_dir=None: [song])
    monkeypatch.setattr(
        enrichment_service,
        "enrich_track_metadata",
        lambda track, **kwargs: (_ for _ in ()).throw(AssertionError("should use cache")),
    )

    summary = enrich_library_batch(music_dir=str(tmp_path), dry_run=True)

    assert summary["analyzed"] == 1
    assert summary["genres_updated"] == 1


def test_cache_recomputes_when_classifier_version_changes(monkeypatch, tmp_path):
    from app.logic.local_ai import enrichment_service
    from app.logic.local_ai.enrichment_service import enrich_library_batch

    cache_path = tmp_path / "cache.json"
    track = tmp_path / "song.mp3"
    track.write_bytes(b"fake audio")
    song = {"path": str(track), "title": "Song", "artist": "Artist", "genre": "", "fileMtime": 1, "fileSize": 2}
    cache_path.write_text(
        json.dumps(
            {
                f"{track}|1|2": {
                    **song,
                    "genre": "Rock",
                    "primary_genre": "Rock",
                    "style": None,
                    "subgenre": None,
                    "mood": [],
                    "tags": [],
                    "metadata_quality": "high",
                    "metadata_source": "heuristic",
                    "classification_confidence": 0.9,
                    "reason": "old",
                    "_cache_meta": {
                        "classifier_version": "legacy-hardcoded-v1",
                        "provider": "fallback",
                        "model": "",
                        "metadata_enabled": False,
                        "track_hash": f"{track}|1|2|Song|Artist|",
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    calls = {"count": 0}

    def _fake_enrich(track, **kwargs):
        calls["count"] += 1
        return {
            **track,
            "genre": "Unknown Genre",
            "primary_genre": "Unknown Genre",
            "style": None,
            "subgenre": None,
            "mood": [],
            "tags": [],
            "metadata_quality": "medium",
            "metadata_source": "fallback",
            "classification_confidence": 0.0,
            "reason": "recomputed",
        }

    monkeypatch.setenv("LOCAL_AI_CACHE_PATH", str(cache_path))
    monkeypatch.setattr(enrichment_service, "scan_music_files", lambda music_dir=None: [song])
    monkeypatch.setattr(enrichment_service, "enrich_track_metadata", _fake_enrich)

    enrich_library_batch(music_dir=str(tmp_path), dry_run=True)

    assert calls["count"] == 1


def test_cache_recomputes_when_model_changes(monkeypatch, tmp_path):
    from app.logic.local_ai import enrichment_service
    from app.logic.local_ai.classifier_base import CLASSIFIER_VERSION
    from app.logic.local_ai.enrichment_service import enrich_library_batch

    cache_path = tmp_path / "cache.json"
    track = tmp_path / "song.mp3"
    track.write_bytes(b"fake audio")
    song = {"path": str(track), "title": "Song", "artist": "Artist", "genre": "", "fileMtime": 1, "fileSize": 2}
    cache_path.write_text(
        json.dumps(
            {
                f"{track}|1|2": {
                    **song,
                    "genre": "Rock",
                    "primary_genre": "Rock",
                    "style": None,
                    "subgenre": None,
                    "mood": [],
                    "tags": [],
                    "metadata_quality": "high",
                    "metadata_source": "local_ai",
                    "classification_confidence": 0.9,
                    "reason": "old",
                    "_cache_meta": {
                        "classifier_version": CLASSIFIER_VERSION,
                        "provider": "ollama",
                        "model": "old-model",
                        "metadata_enabled": True,
                        "track_hash": f"{track}|1|2|Song|Artist|",
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    calls = {"count": 0}

    def _fake_enrich(track, **kwargs):
        calls["count"] += 1
        return {**track, "genre": "Jazz", "primary_genre": "Jazz", "style": None, "subgenre": None, "mood": [], "tags": [], "metadata_quality": "medium", "metadata_source": "local_ai", "classification_confidence": 0.7, "reason": "new model"}

    monkeypatch.setenv("LOCAL_AI_CACHE_PATH", str(cache_path))
    monkeypatch.setenv("LOCAL_AI_METADATA_ENABLED", "true")
    monkeypatch.setenv("LOCAL_AI_MODEL", "new-model")
    monkeypatch.setattr(enrichment_service, "scan_music_files", lambda music_dir=None: [song])
    monkeypatch.setattr(enrichment_service, "enrich_track_metadata", _fake_enrich)

    enrich_library_batch(music_dir=str(tmp_path), dry_run=True, force_local_ai=True)

    assert calls["count"] == 1


def test_get_classifier_uses_fallback_when_ollama_model_missing(monkeypatch):
    from app.logic.local_ai.enrichment_service import get_classifier

    monkeypatch.setenv("LOCAL_AI_METADATA_ENABLED", "true")
    monkeypatch.setenv("LOCAL_AI_MODEL", "definitely-missing-model:zzz")
    monkeypatch.setattr(
        "app.logic.local_ai.enrichment_service.is_ollama_model_available",
        lambda *args, **kwargs: False,
    )

    classifier = get_classifier()
    from app.logic.local_ai.fallback_classifier import FallbackClassifier

    assert isinstance(classifier, FallbackClassifier)


def test_default_local_ai_config_uses_qwen2_5_3b(monkeypatch):
    from app.logic.local_ai.config import get_config

    monkeypatch.delenv("LOCAL_AI_MODEL", raising=False)
    monkeypatch.delenv("LOCAL_AI_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("LOCAL_AI_BATCH_SIZE", raising=False)

    config = get_config()

    assert config.model == "qwen2.5:3b"
    assert config.timeout_seconds == 60
    assert config.batch_size == 5


def test_start_script_suggests_pull_qwen2_5_3b():
    script = Path(__file__).resolve().parents[2] / "scripts" / "start-local-ai-metadata.sh"
    source = script.read_text(encoding="utf-8")

    assert 'MODEL="${LOCAL_AI_MODEL:-qwen2.5:3b}"' in source
    assert "Run: ollama pull qwen2.5:3b" in source


def test_production_classifier_has_no_hardcoded_music_mappings():
    classifier_dir = Path(__file__).resolve().parents[1] / "logic" / "local_ai"
    production_files = [
        classifier_dir / "classification_validator.py",
        classifier_dir / "genre_classifier.py",
        classifier_dir / "fallback_classifier.py",
        classifier_dir / "ollama_classifier.py",
        classifier_dir / "ollama_availability.py",
        classifier_dir / "classifier_base.py",
    ]

    for file_path in production_files:
        source = file_path.read_text(encoding="utf-8")
        for forbidden in FORBIDDEN_HARDCODED_STRINGS:
            assert forbidden not in source, f"{forbidden} found in {file_path.name}"


def test_sidebar_has_no_hardcoded_filter_buttons():
    root = Path(__file__).resolve().parents[2]
    sidebar_html = (root / "browser_extension" / "firefox" / "sidebar" / "sidebar.html").read_text(encoding="utf-8")
    sidebar_js = (root / "browser_extension" / "firefox" / "sidebar" / "sidebar.js").read_text(encoding="utf-8")

    for label in ["Piano", "Nightcore", "Anime", "Electronic", "Rock"]:
        assert f'data-filter="{label}"' not in sidebar_html
        assert f">{label}</button>" not in sidebar_html

    assert "renderDynamicFilters" in sidebar_js
    assert "collectFilterValues" in sidebar_js
    assert 'data-filter="Piano"' not in sidebar_js


def test_process_metadata_stores_video_id_outside_tcon(tmp_path):
    from mutagen.id3 import ID3

    from app.logic.ultimate_downloader import process_metadata

    audio_path = tmp_path / "song.mp3"
    audio_path.write_bytes(b"fake audio")

    process_metadata(str(audio_path), "mp3", "pzXMXGM21YI", meta={"title": "Song", "artist": "Artist"})

    tags = ID3(str(audio_path))
    assert "TCON" not in tags
    assert str(tags["TXXX:YOUTUBE_VIDEO_ID"].text[0]) == "pzXMXGM21YI"


def test_write_audio_metadata_repairs_video_id_from_tcon(tmp_path):
    from mutagen.id3 import ID3, TCON

    from app.logic.local_ai.enrichment_service import write_audio_metadata

    audio_path = tmp_path / "song.mp3"
    audio_path.write_bytes(b"fake audio")
    tags = ID3()
    tags.add(TCON(encoding=3, text="pzXMXGM21YI"))
    tags.save(str(audio_path), v2_version=3)

    write_audio_metadata(str(audio_path), {"genre": "Rock", "videoId": "pzXMXGM21YI"})

    repaired = ID3(str(audio_path))
    assert str(repaired["TCON"].text[0]) == "Rock"
    assert str(repaired["TXXX:YOUTUBE_VIDEO_ID"].text[0]) == "pzXMXGM21YI"


def test_enrich_track_metadata_same_result_twice_uses_cache(monkeypatch, tmp_path):
    from app.logic.local_ai import enrichment_service
    from app.logic.local_ai.enrichment_service import enrich_track_metadata

    cache_path = tmp_path / "cache.json"
    monkeypatch.setenv("LOCAL_AI_CACHE_PATH", str(cache_path))
    monkeypatch.setenv("LOCAL_AI_METADATA_ENABLED", "false")

    calls = {"count": 0}

    class StableClassifier:
        def classify(self, track):
            calls["count"] += 1
            return {
                "title": track.get("title", ""),
                "artist": track.get("artist", ""),
                "album": track.get("album", ""),
                "genre": "Rock",
                "primary_genre": "Rock",
                "style": None,
                "subgenre": None,
                "collection": None,
                "mood": [],
                "tags": ["Rock"],
                "metadata_quality": "medium",
                "metadata_source": "fallback",
                "classification_confidence": 0.5,
                "reason": "stable",
                "videoId": "",
            }

    monkeypatch.setattr(enrichment_service, "get_classifier", lambda **kwargs: StableClassifier())

    track = {"title": "Song", "artist": "Artist", "album": "Album", "path": "/tmp/song.mp3", "fileMtime": 1, "fileSize": 2}
    first = enrich_track_metadata(track)
    second = enrich_track_metadata(track)

    assert first["tags"] == second["tags"]
    assert first["genre"] == second["genre"]
    assert calls["count"] == 1


def test_ollama_classifier_same_track_twice_returns_same_result(monkeypatch):
    from app.logic.local_ai.ollama_classifier import OllamaClassifier

    fixed_response = json.dumps(
        {
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
    )
    monkeypatch.setattr(OllamaClassifier, "_call_ollama", lambda self, prompt: fixed_response)

    classifier = OllamaClassifier(base_url="http://localhost:11434", model="test-model")
    track = {"title": "Nightcore - Die Young", "artist": "Artist", "genre": ""}
    first = classifier.classify(track)
    second = classifier.classify(track)

    assert first["tags"] == second["tags"]
    assert first["genre"] == second["genre"]
    assert first["style"] == second["style"]
    assert "Piano" not in first["tags"]
    assert "Jumpstyle" not in first["tags"]


def test_ollama_classifier_uses_deterministic_options(monkeypatch):
    from app.logic.local_ai.ollama_classifier import OllamaClassifier

    captured: list[dict] = []

    def _fake_post(self, payload_data):
        captured.append(payload_data)
        return json.dumps(
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
                "reason": "Rock track.",
            }
        )

    monkeypatch.setattr(OllamaClassifier, "_post_chat", _fake_post)

    OllamaClassifier(base_url="http://localhost:11434", model="test-model").classify(
        {"title": "Rock Song", "artist": "Artist", "genre": ""}
    )

    assert captured
    options = captured[0].get("options") or {}
    assert options.get("temperature") == 0
    assert options.get("top_p") == 0.1
    assert options.get("seed") == 42
