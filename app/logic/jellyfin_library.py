import logging
import os
import re
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import requests

from app.config.jellyfin_config import JellyfinConfig

log = logging.getLogger(__name__)

_SUPPORTED_AUDIO_EXTS = {".mp3", ".flac", ".m4a", ".opus", ".ogg", ".wav", ".mp4"}

_DANGEROUS_CHARS = re.compile(r'[/\\:*?"<>|]')
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_MULTI_SPACE = re.compile(r"  +")


def sanitize_component(name: str, max_len: int = 200) -> str:
    s = _DANGEROUS_CHARS.sub("", name)
    s = _CONTROL_CHARS.sub("", s)
    s = _MULTI_SPACE.sub(" ", s)
    s = s.strip()
    parts = [p for p in s.replace("..", "_").split("/") if p]
    s = " ".join(parts)
    if not s:
        s = "_"
    return s[:max_len].rstrip(". ") or "_"


def _safe_path(library_path: str, artist: str, album: str, filename: str) -> Path:
    norm_lib = os.path.normpath(os.path.realpath(library_path))
    safe_artist = sanitize_component(artist)
    safe_album = sanitize_component(album)
    safe_name = sanitize_component(filename, max_len=220)
    raw = os.path.join(norm_lib, safe_artist, safe_album, safe_name)
    norm_final = os.path.normpath(raw)
    if not norm_final.startswith(norm_lib + "/") and norm_final != norm_lib:
        raise ValueError(
            f"Path traversal blocked: {norm_final} is outside {norm_lib}"
        )
    return Path(norm_final)


def _resolve_duplicate(path: Path) -> Path:
    if not path.exists():
        return path
    parent = path.parent
    stem = path.stem
    ext = path.suffix
    counter = 1
    while True:
        new = parent / f"{stem} ({counter}){ext}"
        if not new.exists():
            return new
        counter += 1


def _set_permissions(path: Path) -> None:
    try:
        if path.is_dir():
            path.chmod(stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
        else:
            path.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH)
    except OSError as exc:
        log.warning("chmod failed for %s: %s", path, exc)

    try:
        owner = JellyfinConfig.get_music_library_owner()
        group = JellyfinConfig.get_music_library_group()
        if group:
            subprocess.run(
                ["chgrp", group, str(path)],
                capture_output=True, text=True, timeout=10,
            )
        if owner:
            subprocess.run(
                ["chown", f"{owner}:{group}" if group else owner, str(path)],
                capture_output=True, text=True, timeout=10,
            )
    except Exception as exc:
        log.warning("chown/chgrp failed for %s (non-fatal): %s", path, exc)


def _setgid_on_dir(path: Path) -> None:
    try:
        mode = path.stat().st_mode
        if not (mode & stat.S_ISGID):
            path.chmod(mode | stat.S_ISGID)
    except OSError as exc:
        log.warning("setgid failed for %s: %s", path, exc)


def _write_id3_tags(
    file_path: Path,
    title: str,
    artist: str,
    album: str,
    track_number: str,
    year: Optional[str],
    genre: Optional[str],
    comment: Optional[str],
) -> None:
    ext = file_path.suffix.lower()

    try:
        if ext == ".mp3":
            from mutagen.id3 import ID3, ID3NoHeaderError, TIT2, TPE1, TALB, TRCK, TYER, TCON, COMM

            try:
                id3 = ID3(str(file_path))
            except ID3NoHeaderError:
                id3 = ID3()
                id3.save(str(file_path), v2_version=3)
                id3 = ID3(str(file_path))

            if title:
                id3.delall("TIT2")
                id3.add(TIT2(encoding=3, text=title))
            if artist:
                id3.delall("TPE1")
                id3.add(TPE1(encoding=3, text=artist))
            if album:
                id3.delall("TALB")
                id3.add(TALB(encoding=3, text=album))
            if track_number:
                id3.delall("TRCK")
                id3.add(TRCK(encoding=3, text=track_number))
            if year:
                id3.delall("TYER")
                id3.add(TYER(encoding=3, text=str(year)))
            if genre:
                id3.delall("TCON")
                id3.add(TCON(encoding=3, text=genre))
            if comment:
                id3.delall("COMM")
                id3.add(COMM(encoding=3, lang="eng", desc="", text=comment))
            id3.save(str(file_path), v2_version=3, v1=2)

        elif ext in (".mp4", ".m4a"):
            from mutagen.mp4 import MP4

            audio = MP4(str(file_path))
            if title:
                audio["\xa9nam"] = [title]
            if artist:
                audio["\xa9ART"] = [artist]
            if album:
                audio["\xa9alb"] = [album]
            if track_number:
                audio["trkn"] = [(int(track_number), 0)]
            if year:
                audio["\xa9day"] = [str(year)]
            if genre:
                audio["\xa9gen"] = [genre]
            if comment:
                audio["\xa9cmt"] = [comment]
            audio.save()

        elif ext == ".flac":
            from mutagen.flac import FLAC

            audio = FLAC(str(file_path))
            if title:
                audio["title"] = title
            if artist:
                audio["artist"] = artist
            if album:
                audio["album"] = album
            if track_number:
                audio["tracknumber"] = str(track_number)
            if year:
                audio["date"] = str(year)
            if genre:
                audio["genre"] = genre
            if comment:
                audio["comment"] = comment
            audio.save()

        else:
            from mutagen import File

            mfile = File(str(file_path), easy=True)
            if mfile is not None:
                if title:
                    mfile["title"] = title
                if artist:
                    mfile["artist"] = artist
                if album:
                    mfile["album"] = album
                if track_number:
                    mfile["tracknumber"] = str(track_number)
                if year:
                    mfile["date"] = str(year)
                if genre:
                    mfile["genre"] = genre
                mfile.save()

    except Exception as exc:
        log.warning("Failed to write metadata tags to %s: %s", file_path, exc)


def _save_cover(album_dir: Path, cover_data: Optional[bytes]) -> None:
    if not cover_data:
        return
    try:
        cover_path = album_dir / "cover.jpg"
        with open(cover_path, "wb") as f:
            f.write(cover_data)
        _set_permissions(cover_path)
        log.info("Cover saved: %s", cover_path)
    except Exception as exc:
        log.warning("Failed to save cover: %s", exc)


def _convert_with_ffmpeg(input_path: Path, output_format: str, bitrate: str) -> Optional[Path]:
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True, text=True, timeout=10,
        )
    except Exception:
        log.warning("ffmpeg not available, skipping conversion")
        return None

    out_path = input_path.with_suffix(f".{output_format}")
    try:
        args = [
            "ffmpeg", "-y", "-i", str(input_path),
            "-vn", "-acodec", "libmp3lame",
            "-b:a", bitrate,
            "-id3v2_version", "3",
            str(out_path),
        ]
        result = subprocess.run(args, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            log.warning("ffmpeg conversion failed: %s", result.stderr.strip())
            return None
        log.info("Converted %s → %s", input_path, out_path)
        return out_path
    except Exception as exc:
        log.warning("ffmpeg conversion error: %s", exc)
        return None


def _notify_jellyfin() -> None:
    api_key = JellyfinConfig.get_jellyfin_api_key()
    if not api_key:
        log.info("JELLYFIN_API_KEY not set — skipping library scan")
        return
    if not JellyfinConfig.get_jellyfin_auto_scan():
        log.info("JELLYFIN_AUTO_SCAN disabled — skipping library scan")
        return

    url = JellyfinConfig.get_jellyfin_url().rstrip("/")
    try:
        resp = requests.post(
            f"{url}/Library/Refresh",
            headers={"X-Emby-Token": api_key},
            timeout=30,
        )
        if resp.status_code == 204:
            log.info("Jellyfin library scan triggered successfully")
        else:
            log.warning(
                "Jellyfin scan returned %s %s",
                resp.status_code,
                resp.text.strip(),
            )
    except requests.RequestException as exc:
        log.warning("Failed to notify Jellyfin (non-fatal): %s", exc)


def saveTrackToLibrary(
    input_path: str,
    metadata: dict,
    copy: bool = False,
) -> str:
    lib_path = JellyfinConfig.get_music_library_path()

    artist = (metadata.get("artist") or "").strip() or "Unknown Artist"
    album = (metadata.get("album") or "").strip() or "Unknown Album"
    title = (metadata.get("title") or "").strip()
    track_number = (metadata.get("trackNumber") or metadata.get("tracknumber") or "").strip()
    year = metadata.get("year")
    genre = metadata.get("genre") or ""
    source_url = metadata.get("sourceUrl") or ""
    video_id = metadata.get("videoId") or metadata.get("video_id") or ""

    input_path_obj = Path(input_path)
    ext = input_path_obj.suffix.lower()

    if not title:
        title = input_path_obj.stem or "Unknown"

    track_number_str = str(track_number).zfill(2) if track_number else "00"

    safe_filename = f"{track_number_str} - {title}{ext}"
    final_path = _safe_path(lib_path, artist, album, safe_filename)
    final_path = _resolve_duplicate(final_path)
    album_dir = final_path.parent

    try:
        album_dir.mkdir(parents=True, exist_ok=True)
        _set_permissions(album_dir)
        _setgid_on_dir(album_dir)
    except OSError as exc:
        log.warning("Failed to create album dir %s: %s", album_dir, exc)
        raise

    output_format = JellyfinConfig.get_output_format()
    should_convert = output_format != "keep" and output_format in ("mp3", "flac", "m4a", "opus", "ogg")
    if should_convert and ext not in _SUPPORTED_AUDIO_EXTS:
        should_convert = False

    if should_convert:
        converted = _convert_with_ffmpeg(input_path_obj, output_format, JellyfinConfig.get_output_bitrate())
        if converted:
            final_path = _resolve_duplicate(album_dir / converted.name)
            ext = converted.suffix.lower()
            input_for_copy = converted
        else:
            input_for_copy = input_path_obj
    else:
        input_for_copy = input_path_obj

    try:
        if copy:
            shutil.copy2(str(input_for_copy), str(final_path))
            log.info("Copied file: %s → %s", input_for_copy, final_path)
        else:
            os.makedirs(str(album_dir), exist_ok=True)
            tmp_fd, tmp_path_str = tempfile.mkstemp(dir=str(album_dir), suffix=ext)
            os.close(tmp_fd)
            try:
                shutil.copy2(str(input_for_copy), tmp_path_str)
                os.fsync(os.open(tmp_path_str, os.O_RDONLY))
                os.replace(tmp_path_str, str(final_path))
                log.info("Moved file: %s → %s", input_for_copy, final_path)
            except BaseException:
                if os.path.exists(tmp_path_str):
                    os.unlink(tmp_path_str)
                raise
    except OSError as exc:
        log.error("Failed to save file to %s: %s", final_path, exc)
        raise

    comment_parts = []
    if source_url:
        comment_parts.append(f"Source: {source_url}")
    if video_id:
        comment_parts.append(f"VideoId: {video_id}")
    comment = " | ".join(comment_parts) or None

    _write_id3_tags(
        final_path,
        title=title or None,
        artist=artist,
        album=album if album != "Unknown Album" else None,
        track_number=track_number_str,
        year=str(year) if year else None,
        genre=genre or None,
        comment=comment,
    )
    log.info("Metadata written for %s", final_path)

    _set_permissions(final_path)

    cover_data = metadata.get("_cover_bytes")
    if isinstance(metadata.get("cover"), str) and metadata["cover"] and not cover_data:
        try:
            resp = requests.get(metadata["cover"], timeout=15)
            if resp.status_code == 200:
                cover_data = resp.content
        except Exception as exc:
            log.debug("Could not fetch cover from %s: %s", metadata["cover"], exc)

    if cover_data:
        _save_cover(album_dir, cover_data)

    if should_convert and converted and converted != input_for_copy:
        try:
            converted.unlink()
        except OSError:
            pass

    _notify_jellyfin()

    log.info(
        "Library save complete: %s | %s - %s | %s",
        final_path, artist, title, album,
    )
    return str(final_path)
