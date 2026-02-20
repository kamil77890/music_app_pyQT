from fastapi import APIRouter, Request, Query
from app.authorization import login_decorator
from app.logic.api_handler.handle_yt import get_song_by_string

router = APIRouter(tags=["title"])


@login_decorator
@router.get("/title")
async def get_title(request: Request, videoId: str = Query(...)):
    song_data = get_song_by_string(videoId)
    snippet = song_data[0]["snippet"]
    title = snippet["title"]
    return {"title": title}
