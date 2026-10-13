from fastapi import APIRouter, HTTPException, Query

from app.logic.api_handler.handle_yt import get_video_by_id

router = APIRouter(tags=["title"])


@router.get("/title")
async def get_title(videoId: str = Query(...)):
    try:
        item = await get_video_by_id(videoId)
    except Exception:
        raise HTTPException(status_code=502, detail="YouTube lookup failed")

    if not item:
        raise HTTPException(status_code=404, detail="Video not found")

    snippet = item.get("snippet", {}) or {}
    return {"title": snippet.get("title", "")}
