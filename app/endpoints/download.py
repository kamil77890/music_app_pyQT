import logging

from fastapi import APIRouter, BackgroundTasks, Query, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from app.logic.ultimate_downloader import download_song, download_playlist
from app.logic.metadata.add_metadata import verify_metadata
import os

log = logging.getLogger(__name__)

router = APIRouter(tags=["download"])


def _safe_header(value: str) -> str:
    """Encode header value to ASCII-safe string (HTTP headers must be latin-1)."""
    try:
        return value.encode('latin-1', 'replace').decode('latin-1')
    except Exception:
        return str(value)


def _wrap_song_response(result: dict) -> FileResponse:
    """Build a FileResponse from the dict returned by ``download_song``."""
    file_path = result["jellyfin_path"]
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    ext = os.path.splitext(file_path)[1].lstrip(".").lower()
    meta = verify_metadata(file_path, ext) if ext in ("mp3", "mp4", "m4a") else {}

    actual_title = meta.get("title", "") if meta else ""
    if not actual_title or actual_title == "N/A":
        actual_title = os.path.splitext(os.path.basename(file_path))[0]

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
    if meta:
        response.headers["X-Title"] = _safe_header(meta.get("title", "Unknown"))
        response.headers["X-Artist"] = _safe_header(meta.get("artist", "Unknown"))
        response.headers["X-VideoId"] = _safe_header(meta.get("videoId", ""))
    response.headers["X-Jellyfin-Path"] = file_path
    if "legacy_path" in result:
        response.headers["X-Legacy-Path"] = result["legacy_path"]

    return response


def _refresh_recommendations_after_download() -> None:
    from app.logic.recommendations.recommendation_feed import refresh_after_library_change

    refresh_after_library_change(reason="download_complete")


@router.get("/download")
async def download(
    background_tasks: BackgroundTasks,
    videoId: str = Query(default="0"),
    id: str = Query(default="0"),
    playlistId: str = Query(default="0"),
    format: str = Query(default="mp3")
):

    if playlistId != "0":
        file_path = await run_in_threadpool(download_playlist, playlistId, id, format)
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Playlist ZIP not found")
        background_tasks.add_task(_refresh_recommendations_after_download)
        response = FileResponse(
            path=file_path,
            filename=os.path.basename(file_path),
            media_type="application/zip",
        )
        response.background = background_tasks
        return response
    else:
        result = await run_in_threadpool(download_song, videoId, id, format)
        background_tasks.add_task(_refresh_recommendations_after_download)
        response = _wrap_song_response(result)
        response.background = background_tasks
        return response
