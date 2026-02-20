from fastapi import APIRouter, Request
from pydantic import BaseModel
from app.logic.handle_like import handle_like
from app.authorization import login_decorator


class LikeRequest(BaseModel):
    id: str
    liked: bool = False


router = APIRouter(tags=["like"])


@login_decorator
@router.post("/api/like")
async def like_song(request: Request, req: LikeRequest):
    handle_like(video_id=req.id, liked=req.liked)
    return {"message": f"Song {req.id} liked: {req.liked}"}
