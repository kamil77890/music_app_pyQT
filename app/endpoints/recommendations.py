from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError

from app.exceptions.youtube_errors import (
    YouTubeAccessDeniedError,
    YouTubeAPIError,
    YouTubeNotFoundError,
    YouTubeQuotaExceededError,
)
from app.logic.recommendations.advanced_pipeline import run_advanced_pipeline
from app.logic.recommendations.explain import explain_recommendation
from app.logic.recommendations.pipeline import run_pipeline
from app.logic.recommendations.playlist_service import load_playlist
from app.logic.recommendations.user_taste_graph import build_user_taste_graph

router = APIRouter(tags=["Recommendations"])

Mode = Literal["focus", "discover", "fresh"]


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
    mode: Mode = Query("focus"),
    use_llm_rerank: bool = Query(False),
):
    songs = load_playlist()
    if not songs:
        raise HTTPException(404, "playlist empty")

    try:
        result = await run_advanced_pipeline(
            max_results=max_results,
            mode=mode,
            use_llm_rerank=use_llm_rerank,
        )
        profile = result["profile"]
        resolved = result["data"]["songs"]
    except (YouTubeQuotaExceededError, YouTubeAccessDeniedError, YouTubeNotFoundError, YouTubeAPIError) as e:
        _raise_youtube_error(e)

    return {
        "success": True,
        "request_id": result.get("request_id"),
        "profile": profile,
        "confidence": result.get("confidence"),
        "low_confidence": result.get("low_confidence"),
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
    mode: Mode = Query("focus"),
    use_llm_rerank: bool = Query(False),
    max_per_channel: int = Query(2, ge=1, le=5),
    debug_scores: bool = Query(False),
):
    songs = load_playlist()
    if not songs:
        raise HTTPException(404, "playlist empty")

    try:
        result = await run_advanced_pipeline(
            max_results=max_results,
            seed_video_id=seed_video_id,
            mode=mode,
            use_llm_rerank=use_llm_rerank,
            max_per_channel=max_per_channel,
            debug_scores=debug_scores,
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
        profile = build_user_taste_graph()
        return {"success": True, "taste_profile": profile}
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail={"error": str(e)}) from e


@router.get("/recommendations/explain/{video_id}")
async def get_recommendation_explain(video_id: str):
    songs = load_playlist()
    if not songs:
        raise HTTPException(404, "playlist empty")
    graph = build_user_taste_graph()
    return {
        "success": True,
        "explanation": explain_recommendation(video_id, graph, songs),
    }
