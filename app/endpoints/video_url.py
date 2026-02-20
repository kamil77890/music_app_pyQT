import re
from fastapi import APIRouter, Request, Query
from fastapi.responses import JSONResponse
from app.authorization import login_decorator
from app.logic.fetch_video import fetch_info

router = APIRouter(tags=["video"])

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


@login_decorator
@router.get("/video-url")
async def video_url(request: Request, videoId: str = Query(..., min_length=11, max_length=11)):
    if not VIDEO_ID_RE.fullmatch(videoId):
        return JSONResponse(
            {"error": "Nieprawidłowy videoId: oczekiwane 11 znaków [A-Za-z0-9_-]"},
            status_code=400,
        )

    try:
        info = fetch_info(videoId)
    except Exception as e:
        return JSONResponse(
            {"error": "Błąd przetwarzania", "details": str(e)}, status_code=500
        )

    chosen = next(
        (
            f
            for f in info.get("formats", [])
            if f.get("vcodec") != "none" and f.get("acodec") != "none"
        ),
        None,
    )

    if not chosen or "url" not in chosen:
        return JSONResponse({"error": "Brak formatu audio+video"}, status_code=500)

    return {
        "title": info.get("title"),
        "format": chosen.get("format_id"),
        "ext": chosen.get("ext"),
        "mime_type": chosen.get("mime_type"),
        "url": chosen.get("url"),
        "expires_in": info.get("_signature_timestamp"),
    }
