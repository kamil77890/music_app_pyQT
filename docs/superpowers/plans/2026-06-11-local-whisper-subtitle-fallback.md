# Local Whisper Subtitle Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate local Whisper subtitles/lyrics when YouTube captions are unavailable, while keeping audio downloads successful even if subtitle work fails.

**Architecture:** Add a focused `app/logic/subtitles/pipeline.py` module that first tries YouTube captions, then falls back to `faster-whisper`. The main downloader calls this pipeline after metadata processing and before cleanup; tests mock `yt-dlp` and Whisper so no network or model download is required.

**Tech Stack:** Python 3.12, FastAPI project structure, `yt-dlp`, `srt`, `mutagen`, `faster-whisper`, `pytest`.

---

## File Structure

- Create `app/logic/subtitles/pipeline.py`: caption fetch, Whisper fallback, SRT writing, TXT conversion without deleting SRT files, optional MP3 synced lyrics embedding.
- Create `app/tests/test_subtitle_pipeline.py`: unit tests for captions-first behavior, fallback behavior, and non-fatal failure handling.
- Modify `app/logic/ultimate_downloader.py`: call the shared subtitle pipeline for single-song and playlist downloads.
- Modify `pyproject.toml`: add `faster-whisper` dependency.
- Modify `requirements.txt`: add `faster-whisper` dependency if this project keeps `requirements.txt` in sync.
- Modify `.env.example`: document optional subtitle/Whisper environment variables if the file exists.

## Task 1: Add Subtitle Pipeline Tests

**Files:**
- Create: `app/tests/test_subtitle_pipeline.py`

- [ ] **Step 1: Write tests for captions-first, Whisper fallback, and non-fatal failures**

Create `app/tests/test_subtitle_pipeline.py` with this content:

```python
from pathlib import Path
from types import SimpleNamespace

import pytest


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
```

- [ ] **Step 2: Run tests and verify they fail because the module does not exist yet**

Run: `pytest app/tests/test_subtitle_pipeline.py -v`

Expected: FAIL with `ModuleNotFoundError` or import error for `app.logic.subtitles.pipeline`.

## Task 2: Implement Caption Fetching And Shared Subtitle Processing

**Files:**
- Create: `app/logic/subtitles/pipeline.py`
- Test: `app/tests/test_subtitle_pipeline.py`

- [ ] **Step 1: Add the pipeline module with YouTube caption fetch and SRT/TXT processing**

Create `app/logic/subtitles/pipeline.py` with this content:

```python
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import srt
from yt_dlp import YoutubeDL

from app.logic.downloader.yt_dlp_client import _find_cookie_file
from app.logic.subtitles.handle_subtitles import embed_sylt, parse_srt_to_sync

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SubtitleResult:
    source: str
    srt_path: Path
    txt_path: Path


def _preferred_languages() -> list[str]:
    raw = os.environ.get("SUBTITLE_LANGS", "pl,en,en-US")
    langs = [lang.strip() for lang in raw.split(",") if lang.strip()]
    return langs or ["pl", "en", "en-US"]


def _existing_srt(base_dir: Path, basename: str, languages: Iterable[str]) -> Path | None:
    for lang in languages:
        candidate = base_dir / f"{basename}.{lang}.srt"
        if candidate.is_file():
            return candidate
    for candidate in sorted(base_dir.glob(f"{basename}.*.srt")):
        return candidate
    return None


def _available_caption_languages(video_id: str) -> list[str]:
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "nocheckcertificate": True,
        "http_headers": {"User-Agent": "Mozilla/5.0"},
    }
    cookie_file = _find_cookie_file()
    if cookie_file:
        opts["cookiefile"] = cookie_file

    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)

    if not info:
        return []

    languages: list[str] = []
    for source_key in ("subtitles", "automatic_captions"):
        captions = info.get(source_key) or {}
        for lang in captions:
            if lang not in languages:
                languages.append(lang)
    return languages


def _caption_language_order(video_id: str) -> list[str]:
    preferred = _preferred_languages()
    try:
        available = _available_caption_languages(video_id)
    except Exception as exc:
        log.warning("Caption language lookup failed for %s: %s", video_id, exc)
        return preferred

    ordered = [lang for lang in preferred if lang in available]
    ordered.extend(lang for lang in available if lang not in ordered)
    return ordered or preferred


def _fetch_youtube_subtitles(video_id: str, base_dir: Path, basename: str) -> Path | None:
    languages = _caption_language_order(video_id)
    outtmpl = str(base_dir / f"{basename}.%(ext)s")
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": languages,
        "subtitlesformat": "srt/best",
        "outtmpl": outtmpl,
        "noplaylist": True,
        "nocheckcertificate": True,
        "postprocessors": [{"key": "FFmpegSubtitlesConvertor", "format": "srt"}],
        "http_headers": {"User-Agent": "Mozilla/5.0"},
    }
    cookie_file = _find_cookie_file()
    if cookie_file:
        opts["cookiefile"] = cookie_file

    try:
        with YoutubeDL(opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
    except Exception as exc:
        log.warning("Subtitle fetch failed for %s: %s", video_id, exc)
        return None

    return _existing_srt(base_dir, basename, languages)


def _embed_if_supported(audio_path: Path, srt_path: Path) -> None:
    if audio_path.suffix.lower() != ".mp3":
        return
    sync = parse_srt_to_sync(str(srt_path))
    embed_sylt(str(audio_path), sync)


def _process_srt(audio_path: Path, srt_path: Path, source: str) -> SubtitleResult | None:
    try:
        _embed_if_supported(audio_path, srt_path)
        txt_path = _write_srt_text_sidecar(srt_path)
        return SubtitleResult(source=source, srt_path=srt_path, txt_path=txt_path)
    except Exception as exc:
        log.warning("Subtitle processing failed for %s: %s", audio_path, exc)
        return None


def _write_srt_text_sidecar(srt_path: Path) -> Path:
    lyrics_dir = srt_path.parent / "lyrics"
    lyrics_dir.mkdir(exist_ok=True)
    txt_path = lyrics_dir / f"{srt_path.stem}.txt"
    subtitles = list(srt.parse(srt_path.read_text(encoding="utf-8")))
    text = "\n".join(sub.content.strip() for sub in subtitles if sub.content.strip())
    txt_path.write_text(text, encoding="utf-8")
    return txt_path


def _seconds_to_timedelta(seconds: float):
    import datetime as dt

    return dt.timedelta(seconds=max(seconds, 0.0))


def _write_segments_to_srt(segments: Iterable, srt_path: Path) -> Path:
    subtitles = []
    for index, segment in enumerate(segments, 1):
        text = str(getattr(segment, "text", "")).strip()
        if not text:
            continue
        subtitles.append(
            srt.Subtitle(
                index=index,
                start=_seconds_to_timedelta(float(getattr(segment, "start", 0.0))),
                end=_seconds_to_timedelta(float(getattr(segment, "end", 0.0))),
                content=text,
            )
        )
    srt_path.write_text(srt.compose(subtitles), encoding="utf-8")
    return srt_path


def _transcribe_with_whisper(audio_path: Path):
    raise RuntimeError("Whisper transcription is not implemented yet")


def process_song_subtitles(audio_path: str, video_id: str, basename: str) -> SubtitleResult | None:
    audio = Path(audio_path)
    base_dir = audio.parent

    srt_path = _fetch_youtube_subtitles(video_id, base_dir, basename)
    if srt_path:
        return _process_srt(audio, srt_path, "youtube")

    try:
        segments = _transcribe_with_whisper(audio)
        whisper_srt = _write_segments_to_srt(segments, base_dir / f"{basename}.whisper.srt")
    except Exception as exc:
        log.warning("Whisper subtitle generation failed for %s: %s", audio_path, exc)
        return None

    return _process_srt(audio, whisper_srt, "whisper")
```

- [ ] **Step 2: Run the pipeline tests**

Run: `pytest app/tests/test_subtitle_pipeline.py -v`

Expected: PASS for all tests in `test_subtitle_pipeline.py` because Whisper is mocked in fallback tests.

## Task 3: Implement Local Whisper Transcription

**Files:**
- Modify: `app/logic/subtitles/pipeline.py`
- Modify: `pyproject.toml`
- Modify: `requirements.txt`
- Test: `app/tests/test_subtitle_pipeline.py`

- [ ] **Step 1: Add `faster-whisper` to project dependencies**

In `pyproject.toml`, add this dependency inside `[project].dependencies`:

```toml
    "faster-whisper>=1.0.0",
```

If `requirements.txt` lists runtime dependencies, add this line:

```text
faster-whisper>=1.0.0
```

- [ ] **Step 2: Replace the placeholder Whisper function**

In `app/logic/subtitles/pipeline.py`, replace `_transcribe_with_whisper()` with:

```python
def _transcribe_with_whisper(audio_path: Path):
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("local transcription unavailable: install faster-whisper") from exc

    model_name = os.environ.get("WHISPER_MODEL", "base")
    device = os.environ.get("WHISPER_DEVICE", "cpu")
    compute_type = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")

    model = WhisperModel(model_name, device=device, compute_type=compute_type)
    segments, _info = model.transcribe(str(audio_path), language=None)
    return list(segments)
```

- [ ] **Step 3: Add a unit test for Whisper configuration**

Append this test to `app/tests/test_subtitle_pipeline.py`:

```python
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
```

- [ ] **Step 4: Run the pipeline tests**

Run: `pytest app/tests/test_subtitle_pipeline.py -v`

Expected: PASS.

## Task 4: Wire The Pipeline Into Downloads

**Files:**
- Modify: `app/logic/ultimate_downloader.py`
- Test: `app/tests/test_subtitle_pipeline.py`

- [ ] **Step 1: Replace the old subtitle imports**

In `app/logic/ultimate_downloader.py`, replace:

```python
from app.logic.subtitles.handle_subtitles import embed_sylt, parse_srt_to_sync, convert_srt_to_txt
```

with:

```python
from app.logic.subtitles.pipeline import process_song_subtitles
```

- [ ] **Step 2: Replace `process_subtitles()` implementation with a compatibility wrapper**

In `app/logic/ultimate_downloader.py`, replace the whole `process_subtitles` function with:

```python
def process_subtitles(file_path: str, video_id: str, basename: str) -> None:
    try:
        process_song_subtitles(file_path, video_id, basename)
    except Exception as e:
        log.warning("Failed to process subtitles: %s", e)
```

- [ ] **Step 3: Update single-song call site**

In `download_song()`, replace:

```python
        srt_path = os.path.join(base, f"{final_name}.en.srt")
        process_subtitles(final_path, srt_path)
```

with:

```python
        process_subtitles(final_path, clean_video_id, final_name)
```

- [ ] **Step 4: Update playlist call site**

In `download_playlist()`, replace:

```python
            srt_path = os.path.splitext(file_path)[0] + ".en.srt"
            process_subtitles(file_path, srt_path)
```

with:

```python
            basename = os.path.splitext(os.path.basename(file_path))[0]
            process_subtitles(file_path, track.get("id", ""), basename)
```

- [ ] **Step 5: Add a unit test for the compatibility wrapper**

Append this test to `app/tests/test_subtitle_pipeline.py`:

```python
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
```

- [ ] **Step 6: Run tests for subtitle pipeline and downloader import**

Run: `pytest app/tests/test_subtitle_pipeline.py -v`

Expected: PASS.

## Task 5: Document Configuration And Run Verification

**Files:**
- Modify: `.env.example`
- Test: full relevant test suite

- [ ] **Step 1: Document optional environment variables**

If `.env.example` exists, add these lines:

```text
# Subtitle and local transcription settings
SUBTITLE_LANGS=pl,en,en-US
WHISPER_MODEL=base
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
```

- [ ] **Step 2: Run focused tests**

Run: `pytest app/tests/test_subtitle_pipeline.py -v`

Expected: PASS.

- [ ] **Step 3: Run all tests**

Run: `pytest -q`

Expected: PASS. If unrelated existing tests fail, capture the failing test names and error messages before changing anything else.

- [ ] **Step 4: Check worktree diff**

Run: `git diff -- app/logic/subtitles/pipeline.py app/tests/test_subtitle_pipeline.py app/logic/ultimate_downloader.py pyproject.toml requirements.txt .env.example docs/superpowers/plans/2026-06-11-local-whisper-subtitle-fallback.md docs/superpowers/specs/2026-06-11-local-whisper-subtitle-fallback-design.md`

Expected: diff only contains the subtitle fallback implementation, tests, dependency/config documentation, and the planning/spec documents.

## Self-Review

- Spec coverage: captions-first behavior is covered by Tasks 1-2; Whisper fallback by Task 3; main download integration by Task 4; environment configuration and verification by Task 5.
- Placeholder scan: no task relies on unspecified behavior; every code-writing step includes concrete code.
- Type consistency: `process_song_subtitles(audio_path: str, video_id: str, basename: str) -> SubtitleResult | None` is used consistently by tests and `ultimate_downloader.py`.
