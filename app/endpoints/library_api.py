import logging
import os
import re

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, FileResponse

from app.config.jellyfin_config import JellyfinConfig
from app.logic.library_scanner import scan_music_files
from app.logic.ultimate_downloader import download_song, extract_video_id

_YT_VIDEO_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{11}$")

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["library-api"])


@router.get("/health")
async def health():
    return {"ok": True, "service": "music_app_pyQT", "library": JellyfinConfig.get_music_library_path()}


@router.post("/download-library")
async def download_to_library(body: dict = Body(...)):
    url = (body.get("url") or "").strip()
    if not url:
        return JSONResponse({"ok": False, "error": "Missing 'url' field"}, status_code=400)

    candidate_id = extract_video_id(url)
    if not _YT_VIDEO_ID_RE.match(candidate_id):
        return JSONResponse({"ok": False, "error": "Could not extract valid YouTube video ID from URL"}, status_code=400)
    video_id = candidate_id

    try:
        result = await run_in_threadpool(download_song, video_id)
        jellyfin_path = result.get("jellyfin_path", "")
        meta = {}
        if jellyfin_path:
            ext = os.path.splitext(jellyfin_path)[1].lstrip(".").lower()
            if ext in ("mp3", "mp4", "m4a"):
                from app.logic.metadata.add_metadata import verify_metadata
                meta = verify_metadata(jellyfin_path, ext)
        return {
            "ok": True,
            "status": "saved",
            "title": meta.get("title") or os.path.splitext(os.path.basename(jellyfin_path))[0],
            "artist": meta.get("artist") or "Unknown Artist",
            "album": meta.get("album") or "Unknown Album",
            "jellyfin_path": jellyfin_path,
            "videoId": video_id,
        }
    except HTTPException:
        raise
    except Exception as exc:
        log.warning("download-library failed for %s: %s", video_id, exc)
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


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
        raise HTTPException(status_code=403, detail="Path not allowed")

    if not os.path.isfile(norm_path):
        raise HTTPException(status_code=404, detail="File not found")

    filename = os.path.basename(norm_path)
    return FileResponse(path=norm_path, filename=filename, media_type="application/octet-stream")
