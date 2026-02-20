from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from app.authorization import login_decorator
from ..db.db_controller import DbController

router = APIRouter(prefix="/api", tags=["songs"])
db = DbController()


@login_decorator
@router.get("/songs")
async def get_songs(request: Request):
    try:
        data = db.get_all_songs()
        return data
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
