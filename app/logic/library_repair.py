"""Detect and repair broken songs in the local library.

A song is considered "broken" when it is missing a real author/title, has no
embedded cover art, has no lyrics, or its audio is unreadable. Repairs are done
in place using yt-dlp metadata (which costs no YouTube Data API quota); a full
re-download is only used as a last resort when the audio file itself is broken.
"""

import logging
import os
from typing import Any, Optional

from mutagen import File as MutagenFile
from mutagen.id3 import ID3, ID3NoHeaderError
from mutagen.mp4 import MP4
from yt_dlp import YoutubeDL

from app.config.stałe import Parameters
from app.logic.downloader.filename import sanitize_filename
from app.logic.downloader.yt_dlp_client import fetch_metadata, _find_cookie_file
from app.logic.subtitles.handle_subtitles import (
    convert_srt_to_txt,
    embed_sylt,
    parse_srt_to_sync,
)
from app.logic.metadata.add_metadata import verify_metadata

log = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = (".mp3", ".mp4", ".m4a")
_PLACEHOLDER_ARTISTS = {"", "unknown artist", "unknown", "n/a", "various artists"}


def _has_cover(file_path: str, ext: str) -> bool:
    try:
        if ext == ".mp3":
            id3 = ID3(file_path)
            return any(k.startswith("APIC") for k in id3.keys())
        if ext in (".mp4", ".m4a"):
            return "covr" in MP4(file_path)
    except Exception:
        return False
    return False


def _has_lyrics(file_path: str, ext: str) -> bool:
    """True if synced/unsynced lyrics are embedded or a sidecar .txt exists."""
    try:
        if ext == ".mp3":
            id3 = ID3(file_path)
            if any(k.startswith(("SYLT", "USLT")) for k in id3.keys()):
                return True
        elif ext in (".mp4", ".m4a"):
            mp4 = MP4(file_path)
            if "\xa9lyr" in mp4:
                return True
    except Exception:
        pass

    base = os.path.splitext(os.path.basename(file_path))[0]
    lyrics_dir = os.path.join(os.path.dirname(file_path), "lyrics")
    return os.path.isfile(os.path.join(lyrics_dir, base + ".txt"))


def _audio_readable(file_path: str) -> bool:
    try:
        audio = MutagenFile(file_path)
        return audio is not None and getattr(audio, "info", None) is not None
    except Exception:
        return False


def analyze_file(file_path: str) -> dict[str, Any]:
    """Return the set of issues for a single audio file."""
    filename = os.path.basename(file_path)
    ext = os.path.splitext(filename)[1].lower()
    base = os.path.splitext(filename)[0]

    meta = verify_metadata(file_path, ext.lstrip("."))
    title = (meta.get("title") or "").strip()
    artist = (meta.get("artist") or "").strip()
    video_id = (meta.get("videoId") or "").strip()

    issues: list[str] = []
    if not title or title in ("N/A", base):
        issues.append("missing_title")
    if artist.lower() in _PLACEHOLDER_ARTISTS or artist == "N/A":
        issues.append("missing_artist")
    if not video_id or video_id == "N/A" or len(video_id) != 11:
        issues.append("missing_video_id")
    if not _has_cover(file_path, ext):
        issues.append("missing_cover")
    if not _has_lyrics(file_path, ext):
        issues.append("missing_lyrics")
    if not _audio_readable(file_path):
        issues.append("corrupt_audio")

    return {
        "filename": filename,
        "title": title,
        "artist": artist,
        "videoId": video_id if len(video_id) == 11 else "",
        "issues": issues,
    }


def scan_library(music_dir: Optional[str] = None) -> dict[str, Any]:
    """Scan the whole library and report files that have issues."""
    if music_dir is None:
        music_dir = Parameters.get_download_dir()

    broken: list[dict[str, Any]] = []
    total = 0

    if not os.path.isdir(music_dir):
        return {"total": 0, "broken": [], "music_dir": music_dir}

    for root, _dirs, files in os.walk(music_dir):
        for filename in sorted(files):
            if not filename.lower().endswith(SUPPORTED_EXTENSIONS):
                continue
            total += 1
            report = analyze_file(os.path.join(root, filename))
            if report["issues"]:
                broken.append(report)

    return {"total": total, "broken": broken, "broken_count": len(broken), "music_dir": music_dir}


def _fetch_subtitles(video_id: str, base_path: str, basename: str) -> Optional[str]:
    """Download English subtitles as .srt via yt-dlp (no YouTube API quota)."""
    outtmpl = os.path.join(base_path, basename + ".%(ext)s")
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["en", "en-US"],
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

    for cand in (f"{basename}.en.srt", f"{basename}.en-US.srt"):
        path = os.path.join(base_path, cand)
        if os.path.isfile(path):
            return path
    return None


def repair_file(
    file_path: str,
    *,
    fetch_lyrics: bool = True,
    allow_redownload: bool = True,
) -> dict[str, Any]:
    """Repair a single file in place. Returns what was fixed.

    Strategy (cheapest first):
      1. If audio is readable and a videoId is known -> refetch metadata via
         yt-dlp and re-embed title/artist/cover (no API quota), fetch lyrics.
      2. If audio is unreadable and a videoId is known -> re-download.
    """
    from app.logic.ultimate_downloader import download_song, process_metadata

    filename = os.path.basename(file_path)
    ext = os.path.splitext(filename)[1].lower()
    base = os.path.splitext(filename)[0]
    base_dir = os.path.dirname(file_path)

    report = analyze_file(file_path)
    issues = report["issues"]
    video_id = report["videoId"]
    fixed: list[str] = []

    if not issues:
        return {"filename": filename, "status": "ok", "fixed": []}

    # Recover videoId from genre tag was already attempted in verify_metadata.
    if not video_id:
        return {
            "filename": filename,
            "status": "skipped",
            "reason": "no recoverable videoId — cannot fetch correct metadata",
            "issues": issues,
            "fixed": [],
        }

    # Case 2: broken audio -> re-download fully.
    if "corrupt_audio" in issues:
        if not allow_redownload:
            return {"filename": filename, "status": "skipped",
                    "reason": "corrupt audio, redownload disabled", "fixed": []}
        try:
            os.remove(file_path)
        except OSError:
            pass
        new_path = download_song(video_id, sanitize_filename(base), ext.lstrip("."), base_path=base_dir)
        return {"filename": filename, "status": "redownloaded",
                "newPath": os.path.basename(new_path), "fixed": ["audio", "metadata", "cover"]}

    # Case 1: in-place metadata/cover repair via yt-dlp metadata (free).
    meta = fetch_metadata(video_id)
    if meta:
        process_metadata(file_path, ext.lstrip("."), video_id, meta=meta)
        for tag_issue in ("missing_title", "missing_artist", "missing_cover"):
            if tag_issue in issues:
                fixed.append(tag_issue.replace("missing_", ""))

    # Lyrics: fetch + embed (mp3 only for synced lyrics).
    if fetch_lyrics and "missing_lyrics" in issues and ext == ".mp3":
        srt_path = _fetch_subtitles(video_id, base_dir, base)
        if srt_path:
            try:
                sync = parse_srt_to_sync(srt_path)
                embed_sylt(file_path, sync)
                convert_srt_to_txt(srt_path)
                fixed.append("lyrics")
            except Exception as exc:
                log.warning("Lyrics embed failed for %s: %s", filename, exc)

    status = "repaired" if fixed else "unchanged"
    return {"filename": filename, "status": status, "videoId": video_id, "fixed": fixed}


def repair_library(
    *,
    only_filenames: Optional[list[str]] = None,
    fetch_lyrics: bool = True,
    allow_redownload: bool = True,
    music_dir: Optional[str] = None,
) -> dict[str, Any]:
    """Scan and repair every broken file (or a given subset by filename)."""
    if music_dir is None:
        music_dir = Parameters.get_download_dir()

    scan = scan_library(music_dir)
    targets = scan["broken"]
    if only_filenames:
        wanted = set(only_filenames)
        targets = [t for t in targets if t["filename"] in wanted]

    results: list[dict[str, Any]] = []
    for report in targets:
        file_path = os.path.join(music_dir, report["filename"])
        if not os.path.isfile(file_path):
            # Could be in a subdirectory; resolve by walking.
            file_path = _resolve_path(music_dir, report["filename"]) or file_path
        try:
            results.append(
                repair_file(file_path, fetch_lyrics=fetch_lyrics, allow_redownload=allow_redownload)
            )
        except Exception as exc:
            log.exception("Repair failed for %s", report["filename"])
            results.append({"filename": report["filename"], "status": "error", "error": str(exc)})

    repaired = sum(1 for r in results if r.get("status") in ("repaired", "redownloaded"))
    return {
        "scanned": scan["total"],
        "broken": len(scan["broken"]),
        "attempted": len(results),
        "repaired": repaired,
        "results": results,
    }


def _resolve_path(music_dir: str, filename: str) -> Optional[str]:
    for root, _dirs, files in os.walk(music_dir):
        if filename in files:
            return os.path.join(root, filename)
    return None
