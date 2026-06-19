import datetime as dt
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import srt
from yt_dlp import YoutubeDL

from app.logic.downloader.yt_dlp_client import _find_cookie_file
from app.logic.subtitles.handle_subtitles import embed_sylt, parse_srt_to_sync

log = logging.getLogger(__name__)

FAILED_SUBTITLE_VIDEO_IDS: set[str] = set()


class _SubtitleYoutubeDLLogger:
    def debug(self, msg):
        log.debug("yt-dlp subtitles: %s", msg)

    def warning(self, msg):
        log.warning("yt-dlp subtitles: %s", msg)

    def error(self, msg):
        if _is_429_error(msg):
            log.debug("yt-dlp subtitles rate-limit message suppressed: %s", msg)
            return
        log.error("yt-dlp subtitles: %s", msg)


@dataclass(frozen=True)
class SubtitleResult:
    source: str
    srt_path: Path
    txt_path: Path


def _preferred_languages() -> list[str]:
    raw = os.environ.get("SUBTITLES_LANG") or os.environ.get("SUBTITLE_LANGS", "pl")
    langs = [lang.strip() for lang in raw.split(",") if lang.strip()]
    return langs or ["pl"]


def subtitles_enabled() -> bool:
    return os.environ.get("SUBTITLES_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def _retry_on_429_enabled() -> bool:
    return os.environ.get("SUBTITLES_RETRY_ON_429", "true").strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    try:
        return max(int(os.environ.get(name, str(default))), 0)
    except ValueError:
        return default


def _is_429_error(exc) -> bool:
    text = str(exc)
    return "429" in text or "Too Many Requests" in text


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
        "logger": _SubtitleYoutubeDLLogger(),
    }
    cookie_file = _find_cookie_file()
    if cookie_file:
        opts["cookiefile"] = cookie_file

    cookies_from_browser = os.environ.get("YTDLP_COOKIES_FROM_BROWSER", "")
    if cookies_from_browser:
        opts["cookiesfrombrowser"] = (cookies_from_browser,)

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
        if _is_429_error(exc):
            FAILED_SUBTITLE_VIDEO_IDS.add(video_id)
            log.warning(
                "YouTube rate-limited subtitle fetch for videoId=%s; skipping subtitles for this session.",
                video_id,
            )
            return []
        log.warning("Caption language lookup failed for %s: %s", video_id, exc)
        return preferred

    ordered = [lang for lang in preferred if lang in available]
    ordered.extend(lang for lang in available if lang not in ordered)
    return ordered or preferred


def _fetch_youtube_subtitles(video_id: str, base_dir: Path, basename: str) -> Path | None:
    if not video_id:
        return None

    if video_id in FAILED_SUBTITLE_VIDEO_IDS:
        log.info("Skipping subtitles for %s; previous subtitle fetch failed.", video_id)
        return None

    languages = _caption_language_order(video_id)
    if video_id in FAILED_SUBTITLE_VIDEO_IDS:
        return None

    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": languages,
        "subtitlesformat": "srt/best",
        "outtmpl": str(base_dir / f"{basename}.%(ext)s"),
        "noplaylist": True,
        "nocheckcertificate": True,
        "postprocessors": [{"key": "FFmpegSubtitlesConvertor", "format": "srt"}],
        "http_headers": {"User-Agent": "Mozilla/5.0"},
        "logger": _SubtitleYoutubeDLLogger(),
    }
    cookie_file = _find_cookie_file()
    if cookie_file:
        opts["cookiefile"] = cookie_file

    cookies_from_browser = os.environ.get("YTDLP_COOKIES_FROM_BROWSER", "")
    if cookies_from_browser:
        opts["cookiesfrombrowser"] = (cookies_from_browser,)

    max_retries = _int_env("SUBTITLES_MAX_RETRIES", 1) if _retry_on_429_enabled() else 0
    backoff_seconds = _int_env("SUBTITLES_429_BACKOFF_SECONDS", 5)
    attempts = max_retries + 1

    for attempt in range(attempts):
        try:
            with YoutubeDL(opts) as ydl:
                ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
            break
        except Exception as exc:
            if _is_429_error(exc):
                if attempt < max_retries:
                    time.sleep(backoff_seconds)
                    continue
                FAILED_SUBTITLE_VIDEO_IDS.add(video_id)
                log.warning(
                    "YouTube rate-limited subtitle fetch for videoId=%s; skipping subtitles for this session.",
                    video_id,
                )
                return None

            log.warning("Subtitle fetch failed for %s: %s", video_id, exc)
            return None

    return _existing_srt(base_dir, basename, languages)


def _embed_if_supported(audio_path: Path, srt_path: Path) -> None:
    if audio_path.suffix.lower() != ".mp3":
        return
    sync = parse_srt_to_sync(str(srt_path))
    embed_sylt(str(audio_path), sync)


def _write_srt_text_sidecar(srt_path: Path) -> Path:
    lyrics_dir = srt_path.parent / "lyrics"
    lyrics_dir.mkdir(exist_ok=True)
    txt_path = lyrics_dir / f"{srt_path.stem}.txt"
    subtitles = list(srt.parse(srt_path.read_text(encoding="utf-8")))
    text = "\n".join(sub.content.strip() for sub in subtitles if sub.content.strip())
    txt_path.write_text(text, encoding="utf-8")
    return txt_path


def _process_srt(audio_path: Path, srt_path: Path, source: str) -> SubtitleResult | None:
    try:
        _embed_if_supported(audio_path, srt_path)
        txt_path = _write_srt_text_sidecar(srt_path)
        return SubtitleResult(source=source, srt_path=srt_path, txt_path=txt_path)
    except Exception as exc:
        log.warning("Subtitle processing failed for %s: %s", audio_path, exc)
        return None


def _seconds_to_timedelta(seconds: float) -> dt.timedelta:
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


def process_song_subtitles(audio_path: str, video_id: str, basename: str) -> SubtitleResult | None:
    if not subtitles_enabled():
        log.debug("Subtitles disabled; skipping subtitles for %s", video_id)
        return None

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
