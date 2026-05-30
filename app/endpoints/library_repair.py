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
