"""Upload audio files from other devices to the server library."""

import logging
import os
import shutil
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse

from app.config.jellyfin_config import JellyfinConfig
from app.config.stałe import Parameters
from app.logic.jellyfin_library import saveTrackToLibrary
from app.logic.library_scanner import (
    build_and_save_playlist,
    scan_music_files,
    sync_songs_to_db,
)
from app.logic.metadata.add_metadata import verify_metadata

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["upload"])

SUPPORTED_EXTENSIONS = (".mp3", ".mp4", ".m4a", ".flac", ".ogg", ".wav")
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB


def _sanitize_filename(name: str) -> str:
    """Remove path separators and null bytes — keep unicode intact."""
    return name.replace("/", "_").replace("\\", "_").replace("\0", "")


def _cleanup_temp_file(path: str) -> None:
    try:
        if os.path.isfile(path):
            os.remove(path)
            log.info("Removed temp file: %s", path)
    except OSError as exc:
        log.warning("Failed to remove temp file %s: %s", path, exc)


@router.post("/upload")
async def upload_songs(
    files: list[UploadFile] = File(...),
    rescan: bool = Query(True, description="Rebuild playlist.json after upload"),
):
    """Accept one or more audio files and save them to the Jellyfin library.

    Uploaded files are saved to a temporary directory, then moved to the
    Jellyfin library at ``/srv/music/…``.  After saving, optionally rescans
    ``FILEPATH`` to update ``playlist.json``.

    When ``MUSIC_KEEP_LEGACY_COPY=true`` a copy is also kept in ``FILEPATH``.
    """
    temp_dir = JellyfinConfig.get_temp_dir()
    os.makedirs(temp_dir, exist_ok=True)
    keep_legacy = JellyfinConfig.get_keep_legacy_copy()

    saved: list[dict] = []
    errors: list[dict] = []

    for upload in files:
        filename = _sanitize_filename(upload.filename or "unknown.mp3")
        ext = os.path.splitext(filename)[1].lower()

        if ext not in SUPPORTED_EXTENSIONS:
            errors.append({"filename": filename, "error": f"Unsupported format: {ext}"})
            continue

        temp_path = os.path.join(temp_dir, filename)

        try:
            size = 0
            with open(temp_path, "wb") as f:
                while chunk := await upload.read(1024 * 64):
                    size += len(chunk)
                    if size > MAX_FILE_SIZE:
                        f.close()
                        os.remove(temp_path)
                        errors.append({"filename": filename, "error": "File exceeds 100 MB limit"})
                        break
                    f.write(chunk)
                else:
                    meta = verify_metadata(temp_path, ext.lstrip("."))
                    log.info("Uploaded: %s (%d bytes)", filename, size)

                    jellyfin_meta = {
                        "title": meta.get("title") or filename,
                        "artist": meta.get("artist") or "Unknown Artist",
                        "album": meta.get("album") or "Unknown Album",
                        "videoId": meta.get("videoId") or "",
                        "cover": meta.get("cover") or "",
                    }
                    try:
                        jellyfin_path = saveTrackToLibrary(temp_path, jellyfin_meta, copy=True)
                    except Exception as jellyfin_err:
                        log.warning("Failed to save to Jellyfin library: %s", jellyfin_err)
                        jellyfin_path = temp_path

                    # Legacy backup: copy to the original download directory
                    if keep_legacy:
                        legacy_dir = Parameters.get_download_dir()
                        os.makedirs(legacy_dir, exist_ok=True)
                        try:
                            shutil.copy2(temp_path, os.path.join(legacy_dir, filename))
                            log.info("Legacy copy saved: %s/%s", legacy_dir, filename)
                        except OSError as exc:
                            log.warning("Failed to create legacy copy: %s", exc)
                    else:
                        _cleanup_temp_file(temp_path)

                    saved.append({
                        "filename": filename,
                        "title": meta.get("title", filename),
                        "artist": meta.get("artist", "Unknown Artist"),
                        "videoId": meta.get("videoId", ""),
                        "size_bytes": size,
                        "jellyfin_path": jellyfin_path,
                    })
        except Exception as exc:
            log.exception("Failed to save %s", filename)
            errors.append({"filename": filename, "error": str(exc)})
            if os.path.exists(temp_path):
                os.remove(temp_path)

    if rescan and saved:
        songs = scan_music_files()
        build_and_save_playlist(songs)
        inserted = sync_songs_to_db(songs)
    else:
        inserted = 0

    return JSONResponse({
        "uploaded": len(saved),
        "failed": len(errors),
        "inserted_to_db": inserted,
        "files": saved,
        "errors": errors,
    })


@router.delete("/songs/{filename:path}")
async def delete_song(filename: str):
    """Delete a song file from the library and rescan."""
    download_dir = Parameters.get_download_dir()
    file_path = os.path.join(download_dir, _sanitize_filename(filename))

    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    os.remove(file_path)
    log.info("Deleted: %s", filename)

    songs = scan_music_files()
    build_and_save_playlist(songs)

    return {"deleted": filename, "remaining_songs": len(songs)}
