"""Endpoints to find and fix broken songs in the local library."""

import logging
from typing import Optional

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from app.logic import library_repair

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/library", tags=["library"])


class RepairBody(BaseModel):
    filenames: Optional[list[str]] = None
    fetch_lyrics: bool = True
    allow_redownload: bool = True


@router.get("/issues")
async def get_library_issues():
    """Scan the library and list songs with missing author, cover, lyrics, etc."""
    return await run_in_threadpool(library_repair.scan_library)


@router.post("/repair")
async def repair_library(body: RepairBody = RepairBody()):
    """Repair broken songs in place (free) or re-download corrupt audio.

    Optionally pass ``filenames`` to repair only specific files.
    """
    return await run_in_threadpool(
        library_repair.repair_library,
        only_filenames=body.filenames,
        fetch_lyrics=body.fetch_lyrics,
        allow_redownload=body.allow_redownload,
    )


@router.get("/check")
async def check_library_data():
    """Comprehensive data check for every song in the library.

    Returns per-song field status for: title, artist, videoId, cover,
    lyrics, audio health, format, and file size.
    """
    return await run_in_threadpool(library_repair.check_library_data)


@router.post("/check")
async def check_song_data(body: RepairBody = RepairBody()):
    """Comprehensive data check for specific songs, or all if filenames is empty."""
    music_dir = None
    from app.config.stałe import Parameters
    music_dir = Parameters.get_download_dir()

    if body.filenames:
        import os
        result: list[dict] = []
        for fn in body.filenames:
            fp = os.path.join(music_dir, fn)
            if os.path.isfile(fp):
                result.append(library_repair.check_song_data(fp))
        return {"songs": result}
    return await run_in_threadpool(library_repair.check_library_data)
