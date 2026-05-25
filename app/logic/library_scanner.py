"""Scan a music directory for audio files, build playlist.json and sync to DB."""

import json
import logging
import os
from pathlib import Path

from app.config.stałe import Parameters
from app.logic.metadata.add_metadata import verify_metadata

log = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = (".mp3", ".mp4", ".m4a", ".flac", ".ogg", ".wav")


def _get_playlist_dir() -> Path:
    return Path(Parameters.get_download_dir()) / "All Songs"


def _get_playlist_path() -> Path:
    return _get_playlist_dir() / "playlist.json"


def scan_music_files(music_dir: str | None = None) -> list[dict]:
    """Walk *music_dir* (default ``FILEPATH``) and read metadata from every
    supported audio file.  Returns a list of song dicts ready for
    ``playlist.json``."""
    if music_dir is None:
        music_dir = Parameters.get_download_dir()

    if not os.path.isdir(music_dir):
        log.warning("Music directory does not exist: %s", music_dir)
        return []

    songs: list[dict] = []

    for root, _dirs, files in os.walk(music_dir):
        for filename in sorted(files):
            if not filename.lower().endswith(SUPPORTED_EXTENSIONS):
                continue

            file_path = os.path.join(root, filename)
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

            songs.append({
                "title": title,
                "artist": artist,
                "videoId": video_id,
                "cover": cover,
                "filename": filename,
                "path": file_path,
                "viewed": False,
                "duration": 0,
            })

    log.info("Scanned %d audio files in %s", len(songs), music_dir)
    return songs


def build_and_save_playlist(songs: list[dict] | None = None) -> dict:
    """Build ``playlist.json`` from *songs* (or scan if ``None``) and write it
    to ``<FILEPATH>/All Songs/playlist.json``.  Returns the full data dict."""
    if songs is None:
        songs = scan_music_files()

    data = {"songs": songs}

    playlist_dir = _get_playlist_dir()
    playlist_dir.mkdir(parents=True, exist_ok=True)
    playlist_path = _get_playlist_path()

    playlist_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("Saved playlist.json with %d songs to %s", len(songs), playlist_path)
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

            if vid and vid in existing_video_ids:
                continue
            if title.lower() in existing_titles:
                continue

            columns = ["title", "artist", "videoId", "liked"]
            values = [title, artist, vid or None, 0]

            try:
                db.insert("songs", columns, values)
                inserted += 1
            except Exception as exc:
                log.debug("Skip insert for '%s': %s", title, exc)

        db.commit()
        log.info("Inserted %d new songs into DB", inserted)
    finally:
        db.close()

    return inserted


def ensure_playlist_and_db() -> dict:
    """High-level helper: if ``playlist.json`` doesn't exist, scan files,
    create it, and sync to DB.  Returns the playlist data dict."""
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
