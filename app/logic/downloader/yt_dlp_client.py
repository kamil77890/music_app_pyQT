"""Single-pass YouTube audio downloader built on yt-dlp.

One network extraction per video downloads the audio, converts it to the
requested codec and embeds the thumbnail + basic metadata in the same run.
The returned dicts carry everything the rest of the pipeline needs (final
file path, title, artist, thumbnail URL, video id) so no extra YouTube Data
API calls are required downstream.
"""

import logging
import os
from pathlib import Path
from typing import Any, Optional

from yt_dlp import YoutubeDL

log = logging.getLogger(__name__)


def _project_root() -> Path:
    """`app/logic/downloader/yt_dlp_client.py` -> project root."""
    return Path(__file__).resolve().parents[3]


def _find_cookie_file() -> Optional[str]:
    """Look for cookies.txt next to the project root or in the CWD."""
    candidates = [
        _project_root() / "cookies.txt",
        Path.cwd() / "cookies.txt",
    ]
    for path in candidates:
        if path.is_file():
            return str(path)
    return None


def _best_artist(info: dict[str, Any]) -> str:
    """Pick the most accurate artist from yt-dlp metadata.

    YouTube Music entries expose ``artist``/``artists``; regular uploads fall
    back to the channel/uploader name.
    """
    artists = info.get("artists")
    if isinstance(artists, list) and artists:
        return str(artists[0]).strip()
    for key in ("artist", "creator", "uploader", "channel"):
        value = info.get(key)
        if value:
            return str(value).strip()
    return "Unknown Artist"


def _best_title(info: dict[str, Any]) -> str:
    """Prefer the clean ``track`` field over the noisy video ``title``."""
    track = info.get("track")
    if track:
        return str(track).strip()
    return str(info.get("title") or "audio").strip()


def _best_thumbnail(info: dict[str, Any]) -> str:
    """Highest-resolution thumbnail URL from the info dict (no API call)."""
    thumbnails = info.get("thumbnails") or []
    if thumbnails:
        with_res = [t for t in thumbnails if t.get("url")]
        if with_res:
            best = max(
                with_res,
                key=lambda t: (t.get("preference", 0), t.get("height", 0), t.get("width", 0)),
            )
            return best.get("url", "")
    return info.get("thumbnail") or ""


def _final_filepath(entry: dict[str, Any]) -> Optional[str]:
    """Resolve the post-processed output path yt-dlp actually wrote."""
    downloads = entry.get("requested_downloads") or []
    if downloads:
        fp = downloads[0].get("filepath") or downloads[0].get("_filename")
        if fp:
            return fp
    # Fallback for older yt-dlp versions.
    return entry.get("filepath") or entry.get("_filename")


def _entry_to_result(entry: dict[str, Any], audio_format: str) -> Optional[dict[str, Any]]:
    if not entry:
        return None

    filepath = _final_filepath(entry)
    # The recorded path may still carry the pre-conversion extension.
    if filepath:
        root, _ext = os.path.splitext(filepath)
        converted = f"{root}.{audio_format}"
        if os.path.exists(converted):
            filepath = converted

    if not filepath or not os.path.exists(filepath):
        return None

    return {
        "filepath": filepath,
        "id": entry.get("id", ""),
        "title": _best_title(entry),
        "artist": _best_artist(entry),
        "thumbnail": _best_thumbnail(entry),
        "webpage_url": entry.get("webpage_url", ""),
        "duration": entry.get("duration"),
    }


def _build_opts(
    base_path: str,
    audio_format: str,
    quality: str,
    download_subs: bool,
    noplaylist: bool,
    embed_thumbnail: bool,
) -> dict[str, Any]:
    postprocessors: list[dict[str, Any]] = [
        {
            "key": "FFmpegExtractAudio",
            "preferredcodec": audio_format,
            "preferredquality": quality,
        },
        {"key": "FFmpegMetadata", "add_metadata": True},
    ]
    if embed_thumbnail:
        postprocessors.append({"key": "EmbedThumbnail"})

    opts: dict[str, Any] = {
        # Prefer m4a/webm audio-only streams, then fall back gracefully.
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": os.path.join(base_path, "%(title).200B [%(id)s].%(ext)s"),
        "postprocessors": postprocessors,
        "writethumbnail": embed_thumbnail,
        "writesubtitles": download_subs,
        "writeautomaticsub": download_subs,
        "subtitlesformat": "vtt",
        "subtitleslangs": ["en"],
        "noplaylist": noplaylist,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "geo_bypass": True,
        "nocheckcertificate": True,
        "prefer_ffmpeg": True,
        "retries": 3,
        "fragment_retries": 3,
        "concurrent_fragment_downloads": 4,
        "http_headers": {"User-Agent": "Mozilla/5.0"},
    }

    cookie_file = _find_cookie_file()
    if cookie_file:
        opts["cookiefile"] = cookie_file

    return opts


def download_audio(
    url: str,
    base_path: str,
    audio_format: str = "mp3",
    quality: str = "320",
    download_subs: bool = False,
    noplaylist: bool = True,
    embed_thumbnail: bool = True,
) -> list[dict[str, Any]]:
    """Download audio in a single extraction pass.

    Returns one result dict per downloaded track with keys: ``filepath``,
    ``id``, ``title``, ``artist``, ``thumbnail``, ``webpage_url``, ``duration``.
    """
    os.makedirs(base_path, exist_ok=True)
    opts = _build_opts(
        base_path, audio_format, quality, download_subs, noplaylist, embed_thumbnail
    )

    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)

    if not info:
        return []

    entries = info.get("entries")
    if entries is None:
        entries = [info]

    results: list[dict[str, Any]] = []
    for entry in entries:
        result = _entry_to_result(entry, audio_format)
        if result:
            results.append(result)
        elif entry:
            log.warning("Skipping entry with no output file: %s", entry.get("id"))

    return results


def download_song_mp3(
    url: str,
    base_path: str,
    audio_format: str = "mp3",
    quality: str = "320",
    download_subs: bool = False,
) -> list[dict[str, Any]]:
    """Backward-compatible alias for :func:`download_audio` (single video)."""
    return download_audio(
        url,
        base_path,
        audio_format=audio_format,
        quality=quality,
        download_subs=download_subs,
        noplaylist=True,
    )
