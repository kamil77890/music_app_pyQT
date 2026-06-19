import logging
from fastapi import APIRouter, Query
from fastapi.responses import FileResponse
from app.endpoints.api_errors import api_error
from app.logic.subtitles.subtitles_downloader import get_subtitles_as_txt

log = logging.getLogger(__name__)
router = APIRouter(tags=["subtitles"])


@router.get("/subtitles")
async def get_subtitles_txt(videoId: str = Query(...), lang: str = Query(default="en")):
    if not videoId:
        return api_error("MISSING_FIELD", "Missing videoId.", 400)

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
        message = str(e)
        if "429" in message or "Too Many Requests" in message:
            log.warning("YouTube rate-limited subtitle endpoint fetch for videoId=%s; skipping subtitles.", videoId)
            return api_error("YTDLP_RATE_LIMITED", "YouTube rate-limited subtitle fetch.", 429)
        log.warning("Lyrics API error: videoId=%s error=%s", videoId, e)
        return api_error("INTERNAL_ERROR", message, 500)
