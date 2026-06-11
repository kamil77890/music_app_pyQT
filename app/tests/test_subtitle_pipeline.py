from types import SimpleNamespace


def test_process_song_subtitles_uses_youtube_caption(monkeypatch, tmp_path):
    from app.logic.subtitles import pipeline

    audio_path = tmp_path / "song.mp3"
    audio_path.write_bytes(b"fake audio")
    srt_path = tmp_path / "song.en.srt"
    srt_path.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nhello from youtube\n\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(pipeline, "_fetch_youtube_subtitles", lambda *args: srt_path)

    called = {"whisper": False, "embedded": False}
    monkeypatch.setattr(
        pipeline,
        "_transcribe_with_whisper",
        lambda *args: called.__setitem__("whisper", True),
    )
    monkeypatch.setattr(
        pipeline,
        "embed_sylt",
        lambda *args, **kwargs: called.__setitem__("embedded", True),
    )

    result = pipeline.process_song_subtitles(str(audio_path), "abc123", "song")

    assert result is not None
    assert result.source == "youtube"
    assert result.srt_path == srt_path
    assert result.srt_path.exists()
    assert result.txt_path == tmp_path / "lyrics" / "song.en.txt"
    assert result.txt_path.read_text(encoding="utf-8") == "hello from youtube"
    assert called == {"whisper": False, "embedded": True}


def test_process_song_subtitles_falls_back_to_whisper(monkeypatch, tmp_path):
    from app.logic.subtitles import pipeline

    audio_path = tmp_path / "song.mp3"
    audio_path.write_bytes(b"fake audio")

    monkeypatch.setattr(pipeline, "_fetch_youtube_subtitles", lambda *args: None)
    monkeypatch.setattr(
        pipeline,
        "_transcribe_with_whisper",
        lambda *args: [
            SimpleNamespace(start=0.0, end=1.25, text=" pierwszy wers "),
            SimpleNamespace(start=1.25, end=2.5, text="drugi wers"),
        ],
    )
    monkeypatch.setattr(pipeline, "embed_sylt", lambda *args, **kwargs: None)

    result = pipeline.process_song_subtitles(str(audio_path), "abc123", "song")

    assert result is not None
    assert result.source == "whisper"
    assert result.srt_path == tmp_path / "song.whisper.srt"
    assert result.srt_path.exists()
    assert result.txt_path == tmp_path / "lyrics" / "song.whisper.txt"
    assert "pierwszy wers" in result.txt_path.read_text(encoding="utf-8")
    assert "00:00:01,250 --> 00:00:02,500" in result.srt_path.read_text(encoding="utf-8")


def test_process_song_subtitles_returns_none_when_everything_fails(monkeypatch, tmp_path):
    from app.logic.subtitles import pipeline

    audio_path = tmp_path / "song.mp3"
    audio_path.write_bytes(b"fake audio")

    monkeypatch.setattr(pipeline, "_fetch_youtube_subtitles", lambda *args: None)

    def fail_whisper(*args):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(pipeline, "_transcribe_with_whisper", fail_whisper)

    assert pipeline.process_song_subtitles(str(audio_path), "abc123", "song") is None


def test_preferred_languages_uses_env_order(monkeypatch):
    from app.logic.subtitles import pipeline

    monkeypatch.setenv("SUBTITLE_LANGS", "pl, en ,de")
    assert pipeline._preferred_languages() == ["pl", "en", "de"]


def test_transcribe_with_whisper_uses_env_configuration(monkeypatch, tmp_path):
    from app.logic.subtitles import pipeline

    audio_path = tmp_path / "song.mp3"
    audio_path.write_bytes(b"fake audio")
    captured = {}

    class FakeModel:
        def __init__(self, model_name, device, compute_type):
            captured["model_name"] = model_name
            captured["device"] = device
            captured["compute_type"] = compute_type

        def transcribe(self, path, language=None):
            captured["path"] = path
            captured["language"] = language
            return [SimpleNamespace(start=0.0, end=1.0, text="hello")], object()

    import sys

    fake_module = SimpleNamespace(WhisperModel=FakeModel)
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_module)
    monkeypatch.setenv("WHISPER_MODEL", "small")
    monkeypatch.setenv("WHISPER_DEVICE", "cpu")
    monkeypatch.setenv("WHISPER_COMPUTE_TYPE", "int8")

    segments = pipeline._transcribe_with_whisper(audio_path)

    assert segments[0].text == "hello"
    assert captured == {
        "model_name": "small",
        "device": "cpu",
        "compute_type": "int8",
        "path": str(audio_path),
        "language": None,
    }


def test_ultimate_downloader_process_subtitles_delegates(monkeypatch, tmp_path):
    from app.logic import ultimate_downloader

    audio_path = tmp_path / "song.mp3"
    audio_path.write_bytes(b"fake audio")
    called = {}

    def fake_process(file_path, video_id, basename):
        called["file_path"] = file_path
        called["video_id"] = video_id
        called["basename"] = basename

    monkeypatch.setattr(ultimate_downloader, "process_song_subtitles", fake_process)

    ultimate_downloader.process_subtitles(str(audio_path), "abc123", "song")

    assert called == {
        "file_path": str(audio_path),
        "video_id": "abc123",
        "basename": "song",
    }
