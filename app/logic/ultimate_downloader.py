import logging
import os
import re
import zipfile
from typing import Any, Optional
from urllib.parse import urlparse, parse_qs

from fastapi import HTTPException
from mutagen.id3 import ID3, TIT2, TPE1, TCON, ID3NoHeaderError
from mutagen.mp4 import MP4

from app.config.stałe import Parameters
from app.logic.subtitles.handle_subtitles import embed_sylt, parse_srt_to_sync, convert_srt_to_txt
from app.logic.downloader.filename import sanitize_filename
from app.logic.downloader.cleanup import cleanup_temp_files
from app.logic.downloader.yt_dlp_client import download_audio
from app.logic.metadata.add_cover import embed_image_mp3, embed_image_mp4

log = logging.getLogger(__name__)


def _download_dir() -> str:
    return Parameters.get_download_dir()


_TITLE_CLEAN_PATTERNS = [
    r"\s*\[.*?\]", r"\s*\(.*?\)", r"\s*【.*?】",
    r"\s*[|•].*", r"\s*ft\.\s.*", r"\s*feat\.\s.*",
    r"\s*-\s*Official.*", r"\s*-\s*Lyrics.*",
    r"\s*-\s*Audio.*", r"\s*-\s*Video.*",
    r"\s*HD$", r"\s*HQ$", r"\s*4K$",
]


def extract_video_id(video_input: str) -> str:
    if len(video_input) == 11 and all(c.isalnum() or c in "_-" for c in video_input):
        return video_input

    try:
        parsed = urlparse(video_input)

        if parsed.hostname == "youtu.be":
            return parsed.path[1:] if parsed.path.startswith("/") else parsed.path

        if "youtube.com" in (parsed.hostname or ""):
            qs = parse_qs(parsed.query)
            if "v" in qs:
                return qs["v"][0]

        return video_input
    except Exception:
        return video_input


def _clean_title(title: str) -> str:
    cleaned = title
    for pat in _TITLE_CLEAN_PATTERNS:
        cleaned = re.sub(pat, "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip()
    return cleaned or title


def _derive_artist_title(meta: dict[str, Any], file_basename: str) -> tuple[str, str]:
    """Resolve artist/title preferring yt-dlp metadata, falling back to filename.

    yt-dlp's ``artist``/``track`` fields (and channel name) are far more
    accurate than parsing ``Artist - Title`` out of the filename.
    """
    artist = (meta.get("artist") or "").strip()
    title = (meta.get("title") or "").strip()

    if (not artist or artist == "Unknown Artist") and " - " in file_basename:
        parts = file_basename.split(" - ", 1)
        artist = parts[0].strip()
        if not title:
            title = parts[1].strip()

    if not title:
        title = file_basename

    cleaned = _clean_title(title)

    # Many YouTube video titles repeat the artist as a prefix ("Artist - Song").
    if artist and artist != "Unknown Artist":
        prefix = f"{artist} - "
        if cleaned.lower().startswith(prefix.lower()):
            stripped = cleaned[len(prefix):].strip()
            if stripped:
                cleaned = stripped

    return (artist or "Unknown Artist"), cleaned


def process_metadata(
    file_path: str,
    format_ext: str,
    video_id: str,
    meta: Optional[dict[str, Any]] = None,
) -> None:
    """Embed title, artist, videoId and (if needed) cover into the audio file.

    ``meta`` carries the metadata already extracted by yt-dlp
    (``title``/``artist``/``thumbnail``); when present no YouTube Data API call
    is made. ``videoId`` is stored in the genre field (TCON / ©cmt) because the
    rest of the app reads it back from there.
    """
    meta = meta or {}
    try:
        if not os.path.exists(file_path):
            log.warning("File not found for metadata: %s", file_path)
            return

        ext = os.path.splitext(file_path)[1].lower()
        basename = os.path.splitext(os.path.basename(file_path))[0]
        artist, title = _derive_artist_title(meta, basename)
        thumb_url = meta.get("thumbnail") or ""

        if ext == ".mp3":
            try:
                id3 = ID3(file_path)
            except ID3NoHeaderError:
                id3 = ID3()
                id3.save(file_path, v2_version=3)
                id3 = ID3(file_path)

            id3.delall("TIT2")
            id3.add(TIT2(encoding=3, text=title))
            if artist and artist != "Unknown Artist":
                id3.delall("TPE1")
                id3.add(TPE1(encoding=3, text=artist))
            if video_id:
                id3.delall("TCON")
                id3.add(TCON(encoding=3, text=video_id))
            id3.save(file_path, v2_version=3, v1=2)

            # yt-dlp already embeds the thumbnail; only fetch as a fallback.
            if "APIC:" not in id3 and not any(k.startswith("APIC") for k in id3):
                if thumb_url:
                    embed_image_mp3(file_path, image_url=thumb_url)

            log.info("Metadata set (mp3): %s - %s [%s]", artist, title, video_id)

        elif ext in (".mp4", ".m4a"):
            audio = MP4(file_path)
            audio["\xa9nam"] = [title]
            if artist and artist != "Unknown Artist":
                audio["\xa9ART"] = [artist]
            if video_id:
                audio["\xa9cmt"] = [video_id]
            audio.save()

            if "covr" not in MP4(file_path) and thumb_url:
                embed_image_mp4(file_path, image_url=thumb_url)

            log.info("Metadata set (mp4): %s - %s [%s]", artist, title, video_id)

    except Exception as e:
        log.error("process_metadata error: %s", e)


def process_subtitles(file_path: str, srt_path: str) -> None:
    if not os.path.exists(srt_path):
        return
    try:
        sync = parse_srt_to_sync(srt_path)
        embed_sylt(file_path, sync)
        convert_srt_to_txt(srt_path)
    except Exception as e:
        log.warning("Failed to process subtitles: %s", e)


def download_song(videoId: str, id: str = "0", format_ext: str = "mp3", base_path: str = None) -> str:
    try:
        clean_video_id = extract_video_id(videoId)
        base = base_path or _download_dir()
        os.makedirs(base, exist_ok=True)

        # Desired final name: client-provided id, else derived after download.
        desired_name = sanitize_filename(id) if id not in ("0", 0) else None
        if desired_name:
            expected_path = os.path.join(base, f"{desired_name}.{format_ext}")
            if os.path.exists(expected_path):
                log.info("File already exists: %s", expected_path)
                return expected_path

        youtube_url = f"https://www.youtube.com/watch?v={clean_video_id}"
        results = download_audio(
            youtube_url, base, audio_format=format_ext, quality="320"
        )
        if not results:
            raise Exception("Download produced no file")

        track = results[0]
        downloaded_path = track["filepath"]

        # Rename to the requested/clean name for predictable URLs.
        final_name = desired_name or sanitize_filename(track["title"])
        final_path = os.path.join(base, f"{final_name}.{format_ext}")
        if downloaded_path != final_path:
            try:
                if os.path.exists(final_path):
                    os.remove(downloaded_path)
                else:
                    os.rename(downloaded_path, final_path)
            except OSError:
                final_path = downloaded_path

        if not os.path.exists(final_path):
            raise Exception(f"Download failed: {final_path} not created")

        process_metadata(final_path, format_ext, clean_video_id, meta=track)

        srt_path = os.path.join(base, f"{final_name}.en.srt")
        process_subtitles(final_path, srt_path)
        cleanup_temp_files(os.path.join(base, final_name))

        return final_path

    except HTTPException:
        raise
    except Exception as e:
        log.error("Error in download_song: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


def create_playlist_zip(processed_files: list, playlist_title: str) -> str:
    zip_name = sanitize_filename(playlist_title) + ".zip"
    zip_path = os.path.join(_download_dir(), zip_name)

    with zipfile.ZipFile(zip_path, "w") as zipf:
        for file in processed_files:
            zipf.write(file, os.path.basename(file))

    return zip_path


def download_playlist(playlistId: str, audio_format: str = "mp3") -> str:
    try:
        playlist_url = f"https://www.youtube.com/playlist?list={playlistId}"
        playlist_dir = _download_dir()
        os.makedirs(playlist_dir, exist_ok=True)

        results = download_audio(
            playlist_url,
            playlist_dir,
            audio_format=audio_format,
            quality="320",
            noplaylist=False,
        )
        if not results:
            raise Exception("No files were processed")

        processed_files = []
        for track in results:
            file_path = track["filepath"]
            if not os.path.exists(file_path):
                continue
            process_metadata(file_path, audio_format, track.get("id", ""), meta=track)
            srt_path = os.path.splitext(file_path)[0] + ".en.srt"
            process_subtitles(file_path, srt_path)
            processed_files.append(file_path)

        if not processed_files:
            raise Exception("No files were processed")

        return create_playlist_zip(processed_files, f"playlist_{playlistId}")

    except HTTPException:
        raise
    except Exception as e:
        log.error("Error in download_playlist: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
