from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError

from app.exceptions.youtube_errors import (
    YouTubeAccessDeniedError,
    YouTubeAPIError,
    YouTubeNotFoundError,
    YouTubeQuotaExceededError,
)
from app.logic.recommendations.advanced_pipeline import run_advanced_pipeline
from app.logic.recommendations.pipeline import run_pipeline
from app.logic.recommendations.playlist_service import load_playlist
from app.logic.recommendations.taste_profile import build_taste_profile

router = APIRouter(tags=["Recommendations"])


def _raise_youtube_error(exc: Exception) -> None:
    if isinstance(exc, YouTubeQuotaExceededError):
        raise HTTPException(
            status_code=429,
            detail={
                "error": "QUOTA_EXCEEDED",
                "message": str(exc),
                "solution": "Please try again tomorrow or contact administrator",
            },
        ) from exc
    if isinstance(exc, YouTubeAccessDeniedError):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "ACCESS_DENIED",
                "message": str(exc),
                "solution": "Check your YouTube API key configuration",
            },
        ) from exc
    if isinstance(exc, YouTubeNotFoundError):
        raise HTTPException(status_code=404, detail={"error": str(exc)}) from exc
    if isinstance(exc, YouTubeAPIError):
        raise HTTPException(
            status_code=500,
            detail={
                "error": "YOUTUBE_API_ERROR",
                "message": str(exc),
                "solution": "Please try again later",
            },
        ) from exc
    raise exc


@router.get("/recommendations")
async def get_recommendations(
    max_results: int = Query(10, ge=1, le=30),
):
    songs = load_playlist()

    if not songs:
        raise HTTPException(404, "playlist empty")

    try:
        profile, resolved = await run_pipeline(songs, max_results)
    except (YouTubeQuotaExceededError, YouTubeAccessDeniedError, YouTubeNotFoundError, YouTubeAPIError) as e:
        _raise_youtube_error(e)

    return {
        "success": True,
        "profile": profile,
        "data": {
            "songs": resolved,
            "playlist": [],
            "nextPageToken": None,
        },
    }


@router.get("/recommendations/advanced")
async def get_advanced_recommendations(
    max_results: int = Query(10, ge=1, le=30),
    seed_video_id: Optional[str] = Query(None),
):
    songs = load_playlist()
    if not songs:
        raise HTTPException(404, "playlist empty")

    try:
        result = await run_advanced_pipeline(
            max_results=max_results,
            seed_video_id=seed_video_id,
        )
    except (YouTubeQuotaExceededError, YouTubeAccessDeniedError, YouTubeNotFoundError, YouTubeAPIError) as e:
        _raise_youtube_error(e)
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail={"error": str(e)}) from e

    return {"success": True, **result}


@router.get("/recommendations/profile")
async def get_recommendations_profile():
    songs = load_playlist()
    if not songs:
        raise HTTPException(404, "playlist empty")
    try:
        profile = build_taste_profile()
        return {"success": True, "taste_profile": profile}
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail={"error": str(e)}) from e
