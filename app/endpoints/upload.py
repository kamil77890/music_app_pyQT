"""Upload audio files from other devices to the server library."""

import logging
import os
import shutil
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse

from app.config.stałe import Parameters
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


@router.post("/upload")
async def upload_songs(
    files: list[UploadFile] = File(...),
    rescan: bool = Query(True, description="Rebuild playlist.json after upload"),
):
    """Accept one or more audio files and save them to the music library.

    After saving, optionally rescans the library to update ``playlist.json``
    and sync new entries to the database.
    """
    download_dir = Parameters.get_download_dir()
    os.makedirs(download_dir, exist_ok=True)

    saved: list[dict] = []
    errors: list[dict] = []

    for upload in files:
        filename = _sanitize_filename(upload.filename or "unknown.mp3")
        ext = os.path.splitext(filename)[1].lower()

        if ext not in SUPPORTED_EXTENSIONS:
            errors.append({"filename": filename, "error": f"Unsupported format: {ext}"})
            continue

        dest = os.path.join(download_dir, filename)

        try:
            size = 0
            with open(dest, "wb") as f:
                while chunk := await upload.read(1024 * 64):
                    size += len(chunk)
                    if size > MAX_FILE_SIZE:
                        f.close()
                        os.remove(dest)
                        errors.append({"filename": filename, "error": "File exceeds 100 MB limit"})
                        break
                    f.write(chunk)
                else:
                    meta = verify_metadata(dest, ext.lstrip("."))
                    saved.append({
                        "filename": filename,
                        "title": meta.get("title", filename),
                        "artist": meta.get("artist", "Unknown Artist"),
                        "videoId": meta.get("videoId", ""),
                        "size_bytes": size,
                    })
                    log.info("Uploaded: %s (%d bytes)", filename, size)
        except Exception as exc:
            log.exception("Failed to save %s", filename)
            errors.append({"filename": filename, "error": str(exc)})
            if os.path.exists(dest):
                os.remove(dest)

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
