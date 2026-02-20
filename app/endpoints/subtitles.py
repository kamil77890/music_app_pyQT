from fastapi import APIRouter, Request, Query
from fastapi.responses import JSONResponse, FileResponse
from app.authorization import login_decorator
from app.logic.subtitles.subtitles_downloader import get_subtitles_as_txt

router = APIRouter(tags=["subtitles"])


@login_decorator
@router.get("/subtitles")
async def get_subtitles_txt(request: Request, videoId: str = Query(...), lang: str = Query(default="en")):
    if not videoId:
        return JSONResponse({"error": "Missing videoId"}, status_code=400)

    try:
        txt_path = get_subtitles_as_txt(videoId, lang)
        return FileResponse(
            txt_path,
            filename=f"{videoId}.txt",
            media_type="text/plain",
        )
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
