"""
Cloud / Backblaze B2 API — upload and catalog (server-side).
"""

from __future__ import annotations

import logging
import os
import traceback
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config.stałe import Parameters
from app.logic import b2_storage

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/cloud", tags=["cloud"])


class UploadBody(BaseModel):
    """Optional override for music root directory (must exist on server host)."""

    directory: Optional[str] = None


@router.get("/config")
def cloud_config():
    """Public URLs and bucket info for the music library on B2."""
    try:
        return b2_storage.get_cloud_config()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _b2_catalog_detail(exc: Exception) -> str:
    s = str(exc)
    if "SignatureDoesNotMatch" in s:
        return (
            f"{s} — Check .env: B2_KEY_ID + B2_APPLICATION_KEY must be the same key pair from "
            "Backblaze (Application Keys), ENDPOINT_URL = S3 endpoint for that bucket, no spaces/quotes."
        )
    return s


@router.get("/catalog")
def cloud_catalog(max_keys: int = 500):
    """List audio objects under `music/` with direct HTTPS URLs."""
    try:
        items = b2_storage.list_music_objects(max_keys=max_keys)
        return {"items": items, "count": len(items)}
    except Exception as exc:
        logger.exception("GET /cloud/catalog failed: %s", exc)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=_b2_catalog_detail(exc)) from exc


@router.post("/upload")
def cloud_upload(body: UploadBody = UploadBody()):
    """
    Upload all local audio files from the download directory to B2 under `music/`.
    Uses the same root as the app (`FILEPATH` env or default).
    """
    root = body.directory or Parameters.get_download_dir()
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        raise HTTPException(status_code=400, detail=f"Directory not found: {root}")

    try:
        up, fail = b2_storage.upload_directory_to_b2(root, prefix="music")
        return {"ok": True, "uploaded": up, "failed": fail, "root": root}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
