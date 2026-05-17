from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

from app.db import oauth_repository
from app.logic.youtube_import.importer import run_import
from app.logic.youtube_import.oauth_flow import exchange_code, start_auth_url

router = APIRouter(tags=["YouTube Auth"], prefix="/auth/youtube")


@router.get("/start")
async def youtube_auth_start():
    """Return Google OAuth URL to connect YouTube account (optional)."""
    import os

    try:
        result = start_auth_url()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    redirect_uri = os.environ.get(
        "GOOGLE_OAUTH_REDIRECT_URI",
        "http://localhost:8000/auth/youtube/callback",
    ).strip()
    return {
        **result,
        "redirect_uri": redirect_uri,
        "hint": (
            "W Google Cloud → Credentials → OAuth client → "
            "Authorized redirect URIs — wklej dokładnie redirect_uri (http, port 8000, bez końcowego /)."
        ),
    }


@router.get("/callback")
async def youtube_auth_callback(
    code: str = Query(...),
    state: str = Query(...),
):
    try:
        exchange_code(code, state)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return RedirectResponse(url="/auth/youtube/status")


@router.get("/status")
async def youtube_auth_status():
    tokens = oauth_repository.get_tokens("youtube")
    last = tokens.get("last_import_at") if tokens else None
    imported_count = len(oauth_repository.list_imported_by_source(limit=500)) if tokens else 0
    return {
        "connected": tokens is not None,
        "last_import_at": last.isoformat() if last else None,
        "imported_items": imported_count,
        "next_step": (
            "POST /auth/youtube/import to fetch liked videos and playlists"
            if tokens and not last
            else None
        ),
    }


@router.post("/import")
async def youtube_auth_import():
    if not oauth_repository.is_connected():
        raise HTTPException(status_code=400, detail="YouTube account not connected")
    try:
        result = run_import()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"success": True, **result}


@router.delete("/disconnect")
async def youtube_auth_disconnect():
    ok = oauth_repository.delete_tokens("youtube")
    return {"success": True, "disconnected": ok}
