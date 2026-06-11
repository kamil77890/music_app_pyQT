"""Scan a music directory for audio files, build playlist.json and sync to DB."""

import json
import logging
import os
from pathlib import Path

from app.config.stałe import Parameters
from app.logic.atomic import atomic_write_json
from app.logic.color_cache import get_cached_color, set_cached_color
from app.logic.lyrics import existing_lyrics_path, read_lyrics
from app.logic.metadata.add_metadata import verify_metadata
from app.logic.color_extractor import extract_color_palette

log = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = (".mp3", ".mp4", ".m4a", ".flac", ".ogg", ".wav")
SCAN_CACHE_VERSION = 1


def _get_playlist_dir() -> Path:
    return Path(Parameters.get_download_dir()) / "All Songs"


def _get_playlist_path() -> Path:
    return _get_playlist_dir() / "playlist.json"


def _get_scan_cache_path() -> Path:
    return _get_playlist_dir() / "scan_cache.json"


def _file_signature(file_path: str) -> dict:
    stat = os.stat(file_path)
    return {
        "mtime_ns": stat.st_mtime_ns,
        "size": stat.st_size,
    }


def _load_scan_cache() -> dict:
    path = _get_scan_cache_path()
    if not path.is_file():
        return {"version": SCAN_CACHE_VERSION, "files": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("files"), dict):
            return data
    except Exception:
        pass
    return {"version": SCAN_CACHE_VERSION, "files": {}}


def _save_scan_cache(cache: dict) -> None:
    atomic_write_json(_get_scan_cache_path(), {"version": SCAN_CACHE_VERSION, "files": cache.get("files", {})})


def _public_song(song: dict) -> dict:
    return {
        key: value
        for key, value in song.items()
        if not key.startswith("_")
    }


def _hash_text(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _lyrics_metadata(file_path: str, filename: str, song: dict) -> dict:
    sidecar = existing_lyrics_path(song)
    if sidecar is not None:
        text = sidecar.read_text(encoding="utf-8")
        return {
            "hasLyrics": True,
            "lyricsPath": str(sidecar),
            "lyricsFormat": sidecar.suffix.lstrip("."),
            "lyricsHash": _hash_text(text),
            "lyricsUpdatedAt": str(int(sidecar.stat().st_mtime)),
        }

    embedded = _read_lyrics(file_path, filename)
    if embedded:
        return {
            "hasLyrics": True,
            "lyricsPath": None,
            "lyricsFormat": "embedded",
            "lyricsHash": _hash_text(embedded),
            "lyricsUpdatedAt": None,
        }

    return {
        "hasLyrics": False,
        "lyricsPath": None,
        "lyricsFormat": None,
        "lyricsHash": None,
        "lyricsUpdatedAt": None,
    }


def _build_song_entry(file_path: str, filename: str, cached_song: dict | None = None) -> dict:
    if cached_song:
        song = _public_song(dict(cached_song))
        stat = _file_signature(file_path)
        song.update({
            "filename": filename,
            "path": file_path,
            "fileMtime": stat["mtime_ns"],
            "fileSize": stat["size"],
        })

        cover = song.get("cover", "")
        color_data = get_cached_color(cover)
        if color_data is not None:
            song["dominantColor"] = color_data.get("dominantColor")
            song["colorPalette"] = color_data.get("colorPalette")

        central_lyrics = read_lyrics(song, include_text=False)
        if central_lyrics.get("hasLyrics"):
            song.update(central_lyrics)

        return _public_song(song)

    ext = os.path.splitext(filename)[1].lstrip(".").lower()

    try:
        meta = verify_metadata(file_path, ext)
    except Exception as exc:
        log.warning("Cannot read metadata for %s: %s", filename, exc)
        meta = {}

    title = meta.get("title") or os.path.splitext(filename)[0]
    artist = meta.get("artist") or "Unknown Artist"
    video_id = meta.get("videoId") or ""
    cover = meta.get("cover") or ""

    if title in ("N/A", ""):
        title = os.path.splitext(filename)[0]
    if artist == "N/A":
        artist = "Unknown Artist"
    if video_id == "N/A":
        video_id = ""

    song = {
        "title": title,
        "artist": artist,
        "videoId": video_id,
        "cover": cover,
        "filename": filename,
        "path": file_path,
        "viewed": False,
        "duration": 0,
    }

    color_data = get_cached_color(cover) or {"dominantColor": None, "colorPalette": None}
    if cached_song and not color_data.get("dominantColor") and cached_song.get("dominantColor"):
        color_data = {
            "dominantColor": cached_song.get("dominantColor"),
            "colorPalette": cached_song.get("colorPalette"),
        }
    song["dominantColor"] = color_data.get("dominantColor")
    song["colorPalette"] = color_data.get("colorPalette")

    lyrics = _lyrics_metadata(file_path, filename, song)
    song.update(lyrics)

    stat = _file_signature(file_path)
    song["fileMtime"] = stat["mtime_ns"]
    song["fileSize"] = stat["size"]
    return _public_song(song)


def _extract_embedded_lyrics(file_path: str, ext: str) -> str:
    """Extract lyrics embedded in the audio file's metadata tags."""
    try:
        if ext in (".mp3",):
            from mutagen.id3 import ID3
            id3 = ID3(file_path)
            # USLT (unsynced lyrics)
            for key in id3:
                if key.startswith("USLT"):
                    return str(id3[key].text).strip()
            # SYLT (synced lyrics) — just return text lines
            for key in id3:
                if key.startswith("SYLT"):
                    return str(id3[key].text).strip()
        elif ext in (".mp4", ".m4a"):
            from mutagen.mp4 import MP4
            mp4 = MP4(file_path)
            if "\xa9lyr" in mp4:
                return str(mp4["\xa9lyr"][0]).strip()
    except Exception:
        pass
    return ""


def _read_lyrics(file_path: str, filename: str) -> str:
    """Read lyrics from embedded tags or sidecar files next to the audio."""
    base = os.path.splitext(filename)[0]
    base_dir = os.path.dirname(file_path)
    ext = os.path.splitext(filename)[1].lower()

    # 1. Embedded lyrics in audio metadata
    embedded = _extract_embedded_lyrics(file_path, ext)
    if embedded:
        return embedded

    # 2. Sidecar .txt in a lyrics/ subdirectory
    lyrics_txt = os.path.join(base_dir, "lyrics", base + ".txt")
    if os.path.isfile(lyrics_txt):
        try:
            with open(lyrics_txt, encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            pass

    # 3. .en.srt in lyrics/ subdirectory
    lyrics_srt = os.path.join(base_dir, "lyrics", base + ".en.srt")
    if os.path.isfile(lyrics_srt):
        try:
            with open(lyrics_srt, encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            pass

    # 4. .en.srt next to the audio file
    srt_sidecar = os.path.join(base_dir, base + ".en.srt")
    if os.path.isfile(srt_sidecar):
        try:
            with open(srt_sidecar, encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            pass

    return ""


def scan_music_files(music_dir: str | None = None, force: bool = False) -> list[dict]:
    """Walk *music_dir* and return song dicts ready for ``playlist.json``.

    Unchanged files are restored from ``scan_cache.json`` so metadata, lyrics and
    color lookups are not repeated on every scan.
    """
    if music_dir is None:
        music_dir = Parameters.get_download_dir()

    if not os.path.isdir(music_dir):
        log.warning("Music directory does not exist: %s", music_dir)
        return []

    cache = _load_scan_cache()
    cached_files = cache.get("files", {}) if not force else {}
    songs: list[dict] = []
    seen: set[str] = set()

    for root, _dirs, files in os.walk(music_dir):
        for filename in sorted(files):
            if not filename.lower().endswith(SUPPORTED_EXTENSIONS):
                continue

            file_path = os.path.join(root, filename)
            rel_path = os.path.relpath(file_path, music_dir)
            seen.add(rel_path)
            signature = _file_signature(file_path)
            cached_entry = cached_files.get(rel_path)
            cached_song = None

            if (
                not force
                and isinstance(cached_entry, dict)
                and cached_entry.get("signature") == signature
                and isinstance(cached_entry.get("song"), dict)
            ):
                cached_song = cached_entry["song"]

            song = _build_song_entry(file_path, filename, cached_song)
            songs.append(song)
            cached_files[rel_path] = {
                "signature": signature,
                "song": _public_song(song),
            }

    for rel_path in list(cached_files):
        if rel_path not in seen:
            cached_files.pop(rel_path, None)

    cache["files"] = cached_files
    _save_scan_cache(cache)
    return songs


def build_and_save_playlist(songs: list[dict] | None = None) -> dict:
    """Build ``playlist.json`` from *songs* and write it atomically."""
    if songs is None:
        songs = scan_music_files()

    data = {"songs": songs}

    playlist_dir = _get_playlist_dir()
    playlist_path = _get_playlist_path()

    atomic_write_json(playlist_path, data)
    return data


def sync_songs_to_db(songs: list[dict]) -> int:
    """Insert scanned songs into the legacy ``songs`` SQLite table.

    Skips songs that already exist (matched by ``videoId`` or ``title``).
    Returns the number of newly inserted rows.
    """
    from app.db.db_controller import DbController

    db = DbController()
    inserted = 0

    try:
        existing_video_ids: set[str] = set()
        existing_titles: set[str] = set()

        for row in db.get_all_songs():
            if len(row) > 4 and row[4]:
                existing_video_ids.add(row[4])
            if len(row) > 1 and row[1]:
                existing_titles.add(row[1].strip().lower())

        for song in songs:
            vid = song.get("videoId", "").strip()
            title = song.get("title", "").strip()
            artist = song.get("artist", "Unknown Artist").strip()
            cover = song.get("cover", "")

            if vid and vid in existing_video_ids:
                continue
            if title.lower() in existing_titles:
                continue

            color_data = get_cached_color(cover)
            if color_data is None:
                color_data = extract_color_palette(cover) if cover else {"dominantColor": None, "colorPalette": None}
                set_cached_color(cover, color_data)

            color_palette_json = json.dumps(color_data.get("colorPalette")) if color_data.get("colorPalette") else None

            columns = [
                "title",
                "artist",
                "videoId",
                "liked",
                "path",
                "file_mtime",
                "file_size",
                "lyrics_path",
                "lyrics_hash",
                "lyrics_updated_at",
                "has_lyrics",
                "dominant_color",
                "color_palette",
            ]
            values = [
                title,
                artist,
                vid or None,
                0,
                song.get("path"),
                song.get("fileMtime"),
                song.get("fileSize"),
                song.get("lyricsPath"),
                song.get("lyricsHash"),
                song.get("lyricsUpdatedAt"),
                1 if song.get("hasLyrics") else 0,
                color_data.get("dominantColor"),
                color_palette_json,
            ]

            try:
                db.insert("songs", columns, values)
                inserted += 1
            except Exception as exc:
                log.debug("Skip insert for '%s': %s", title, exc)

        db.commit()
    finally:
        db.close()

    return inserted


def ensure_playlist_and_db() -> dict:
    """High-level helper: if ``playlist.json`` doesn't exist, scan files,
    create it, and sync to DB. Returns the playlist data dict."""
    playlist_path = _get_playlist_path()

    if playlist_path.is_file():
        data = json.loads(playlist_path.read_text(encoding="utf-8"))
        return data

    log.info("playlist.json not found — scanning music files…")
    songs = scan_music_files()

    if not songs:
        log.warning("No audio files found, returning empty playlist")
        return {"songs": []}

    data = build_and_save_playlist(songs)
    sync_songs_to_db(songs)
    return data


def inject_lyrics_text(songs: list[dict], include_text: bool = True) -> list[dict]:
    out: list[dict] = []
    for song in songs:
        item = dict(song)
        lyrics = read_lyrics(song, include_text=include_text)
        item.update(lyrics)
        if include_text and item.get("lyricsText"):
            item["lyrics"] = item.pop("lyricsText")
        out.append(item)
    return out
