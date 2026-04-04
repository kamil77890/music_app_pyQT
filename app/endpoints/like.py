from fastapi import APIRouter
from pydantic import BaseModel
from app.logic.handle_like import handle_like


class LikeRequest(BaseModel):
    id: str
    liked: bool = False


router = APIRouter(tags=["like"])


@router.post("/api/like")
async def like_song(req: LikeRequest):
    handle_like(video_id=req.id, liked=req.liked)
    return {"message": f"Song {req.id} liked: {req.liked}"}
