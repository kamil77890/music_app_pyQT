from fastapi import APIRouter, Query, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from app.logic.ultimate_downloader import download_song, download_playlist
from app.logic.metadata.add_metadata import verify_metadata
import os

router = APIRouter(tags=["download"])


def _safe_header(value: str) -> str:
    """Encode header value to ASCII-safe string (HTTP headers must be latin-1)."""
    try:
        return value.encode('latin-1', 'replace').decode('latin-1')
    except Exception:
        return str(value)


def wrap_file_response(file_path: str):
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    # Get actual metadata from the file
    ext = os.path.splitext(file_path)[1].lstrip(".").lower()
    meta = verify_metadata(file_path, ext) if ext in ("mp3", "mp4", "m4a") else {}

    # Use actual title as filename if available, fallback to basename
    actual_title = meta.get("title", "") if meta else ""
    if not actual_title or actual_title == "N/A":
        actual_title = os.path.splitext(os.path.basename(file_path))[0]

    # Build proper filename (ASCII-safe for HTTP headers)
    artist = meta.get("artist", "") if meta else ""
    if artist and artist != "N/A":
        download_filename = f"{artist} - {actual_title}.{ext}"
    else:
        download_filename = f"{actual_title}.{ext}"

    response = FileResponse(
        path=file_path,
        filename=download_filename,
        media_type="application/octet-stream",
    )

    # Add metadata headers (must be ASCII/latin-1 safe)
    if meta:
        response.headers["X-Title"] = _safe_header(meta.get("title", "Unknown"))
        response.headers["X-Artist"] = _safe_header(meta.get("artist", "Unknown"))
        response.headers["X-VideoId"] = _safe_header(meta.get("videoId", ""))

    return response


@router.get("/download")
async def download(
    videoId: str = Query(default="0"),
    id: str = Query(default="0"),
    playlistId: str = Query(default="0"),
    format: str = Query(default="mp3")
):

    if playlistId != "0":
        file_path = await run_in_threadpool(download_playlist, playlistId, id, format)
    else:
        file_path = await run_in_threadpool(download_song, videoId, id, format)

    return wrap_file_response(file_path)
