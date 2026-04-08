import logging
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, FileResponse
from app.logic.subtitles.subtitles_downloader import get_subtitles_as_txt

log = logging.getLogger(__name__)
router = APIRouter(tags=["subtitles"])


@router.get("/subtitles")
async def get_subtitles_txt(videoId: str = Query(...), lang: str = Query(default="en")):
    if not videoId:
        return JSONResponse({"error": "Missing videoId"}, status_code=400)

    try:
        log.info("Lyrics API request: videoId=%s lang=%s", videoId, lang)
        txt_path = get_subtitles_as_txt(videoId, lang)
        log.info("Lyrics API response: videoId=%s status=success", videoId)
        return FileResponse(
            txt_path,
            filename=f"{videoId}.txt",
            media_type="text/plain",
        )
    except Exception as e:
        log.error("Lyrics API error: videoId=%s error=%s", videoId, e)
        return JSONResponse({"error": str(e)}, status_code=500)
