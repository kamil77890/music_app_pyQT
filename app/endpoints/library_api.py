import logging
import os
import re

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, FileResponse

from app.config.jellyfin_config import JellyfinConfig
from app.endpoints.api_errors import api_error
from app.logic.library_scanner import scan_music_files
from app.logic.ultimate_downloader import download_song, extract_video_id

_YT_VIDEO_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{11}$")

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["library-api"])


def _download_error_code(exc: HTTPException) -> str:
    header_code = (exc.headers or {}).get("X-Error-Code")
    if header_code:
        return header_code
    detail = str(exc.detail or "")
    if "403" in detail or "blocked" in detail or "Forbidden" in detail:
        return "YTDLP_FORBIDDEN"
    if "429" in detail or "rate-limit" in detail or "Too Many Requests" in detail:
        return "YTDLP_RATE_LIMITED"
    if exc.status_code == 422 or "without an audio file" in detail or "file not created" in detail:
        return "NO_OUTPUT_FILE"
    return "INTERNAL_ERROR"


@router.get("/health")
async def health():
    return {"ok": True, "service": "music_app_pyQT", "library": JellyfinConfig.get_music_library_path()}


@router.post("/download-library")
async def download_to_library(body: dict = Body(...)):
    url = (body.get("url") or "").strip()
    if not url:
        return api_error("MISSING_FIELD", "Missing 'url' field.", 400)

    candidate_id = extract_video_id(url)
    if not _YT_VIDEO_ID_RE.match(candidate_id):
        return api_error("INVALID_URL", "This is not a valid YouTube URL.", 400)
    video_id = candidate_id

    try:
        result = await run_in_threadpool(download_song, video_id)
        jellyfin_path = result.get("jellyfin_path", "")
        meta = {}
        if jellyfin_path:
            ext = os.path.splitext(jellyfin_path)[1].lstrip(".").lower()
            if ext in ("mp3", "mp4", "m4a"):
                from app.logic.metadata.add_metadata import verify_metadata
                try:
                    meta = verify_metadata(jellyfin_path, ext)
                except Exception as meta_err:
                    log.warning("verify_metadata failed for %s: %s", jellyfin_path, meta_err)
        return {
            "ok": True,
            "status": "saved",
            "title": meta.get("title") or os.path.splitext(os.path.basename(jellyfin_path))[0],
            "artist": meta.get("artist") or "Unknown Artist",
            "album": meta.get("album") or "Unknown Album",
            "jellyfin_path": jellyfin_path,
            "videoId": video_id,
        }
    except HTTPException as exc:
        error_code = _download_error_code(exc)
        message = str(exc.detail) if exc.detail else "Request failed."
        return api_error(error_code, message, exc.status_code, detail=message)
    except Exception as exc:
        log.warning("download-library failed for %s: %s", video_id, exc)
        return api_error("INTERNAL_ERROR", str(exc), 500)


@router.get("/library/songs")
async def library_songs(
    q: str = Query(default=""),
    limit: int = Query(default=200, ge=1, le=1000),
):
    lib_path = JellyfinConfig.get_music_library_path()
    if not os.path.isdir(lib_path):
        return {"songs": [], "total": 0, "library_path": lib_path}

    songs = scan_music_files(lib_path)
    songs.sort(key=lambda s: s.get("title", "").lower())

    if q:
        ql = q.lower()
        songs = [
            s for s in songs
            if ql in s.get("title", "").lower()
            or ql in s.get("artist", "").lower()
            or ql in s.get("album", "").lower()
        ]

    total = len(songs)
    songs = songs[:limit]

    return {
        "songs": songs,
        "total": total,
        "library_path": lib_path,
    }


@router.get("/library/stream")
async def library_stream(path: str = Query(..., description="Absolute path to file within music library")):
    lib_path = JellyfinConfig.get_music_library_path()
    norm_lib = os.path.normpath(os.path.realpath(lib_path))
    norm_path = os.path.normpath(os.path.realpath(path))

    if not norm_path.startswith(norm_lib + "/") and norm_path != norm_lib:
        return api_error("PATH_TRAVERSAL_BLOCKED", "Path is outside the music library.", 403)

    if not os.path.isfile(norm_path):
        return api_error("FILE_NOT_FOUND", "File not found.", 404)

    filename = os.path.basename(norm_path)
    return FileResponse(path=norm_path, filename=filename, media_type="application/octet-stream")
