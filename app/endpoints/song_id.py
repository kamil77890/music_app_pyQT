from fastapi import APIRouter, Request
from app.authorization import login_decorator
from ..db.db_controller import DbController

router = APIRouter(tags=["id"])

db = DbController()


@login_decorator
@router.get("/get/id")
async def get_songs(request: Request):
    try:
        last_id = db.get_last_song_id()
        return last_id if last_id is not None else 0
    except Exception as e:
        return {"error": str(e)}
