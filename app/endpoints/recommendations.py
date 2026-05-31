import logging
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from app.exceptions.youtube_errors import (
    YouTubeAccessDeniedError,
    YouTubeAPIError,
    YouTubeNotFoundError,
    YouTubeQuotaExceededError,
)
from app.logic.recommendations.advanced_pipeline import run_advanced_pipeline
from app.logic.recommendations.explain import explain_recommendation
from app.logic.recommendations.playlist_service import load_playlist
from app.logic.recommendations.user_taste_graph import build_user_taste_graph

router = APIRouter(tags=["Recommendations"])
log = logging.getLogger(__name__)

Mode = Literal["focus", "discover", "fresh"]


class ReferencePlaylistRequest(BaseModel):
    url: str = Field(..., min_length=3)
    limit: int = Field(100, ge=1, le=200)


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
    max_results: int = Query(25, ge=1, le=30),
    mode: Mode = Query("focus"),
    use_llm_rerank: bool = Query(False),
    refresh: bool = Query(False),
):
    songs = load_playlist()
    if not songs:
        raise HTTPException(404, "playlist empty")

    try:
        from app.logic.recommendations.recommendation_feed import get_feed, refresh_feed

        feed = get_feed(limit=max_results)
        if refresh or not feed.get("items"):
            await refresh_feed(
                max_results=max_results,
                mode=mode,
                replace=True,
                reason="api_refresh" if refresh else "api_empty_cache",
            )
            feed = get_feed(limit=max_results)
    except (YouTubeQuotaExceededError, YouTubeAccessDeniedError, YouTubeNotFoundError, YouTubeAPIError) as e:
        _raise_youtube_error(e)
    except SQLAlchemyError as e:
        log.exception("Recommendation endpoint database error")
        raise HTTPException(status_code=500, detail={"error": str(e)}) from e
    except Exception as e:
        log.exception("Recommendation endpoint failed")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "RECOMMENDATION_PIPELINE_ERROR",
                "type": type(e).__name__,
                "message": str(e),
            },
        ) from e

    return {
        "success": True,
        "cached": True,
        "updatedAt": feed.get("updatedAt"),
        "request_id": feed.get("requestId"),
        "profile": feed.get("profile") or {"source": "recommendation_feed", "mode": "cached"},
        "confidence": feed.get("lastConfidence"),
        "low_confidence": None,
        "data": {
            "songs": feed.get("items", []),
            "playlist": [],
            "nextPageToken": None,
        },
    }


@router.get("/recommendations/advanced")
async def get_advanced_recommendations(
    max_results: int = Query(25, ge=1, le=30),
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
        log.exception("Advanced recommendation endpoint database error")
        raise HTTPException(status_code=500, detail={"error": str(e)}) from e
    except Exception as e:
        log.exception("Advanced recommendation endpoint failed")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "RECOMMENDATION_PIPELINE_ERROR",
                "type": type(e).__name__,
                "message": str(e),
            },
        ) from e

    return {"success": True, **result}


@router.get("/recommendations/feed")
async def get_recommendation_feed(limit: int = Query(25, ge=1, le=200)):
    """Instant, pre-computed recommendations gathered by the background service."""
    from app.logic.recommendations.recommendation_feed import get_feed

    feed = get_feed(limit=limit)
    return {"success": True, **feed}


@router.post("/recommendations/feed/refresh")
async def refresh_recommendation_feed(
    max_results: int = Query(25, ge=1, le=50),
    mode: Mode = Query("discover"),
    replace: bool = Query(True),
):
    """Manually trigger a discovery pass and store it in the cache."""
    from app.logic.recommendations.recommendation_feed import refresh_feed

    try:
        return {
            "success": True,
            **await refresh_feed(
                max_results=max_results,
                mode=mode,
                replace=replace,
                reason="manual_refresh",
            ),
        }
    except (YouTubeQuotaExceededError, YouTubeAccessDeniedError, YouTubeNotFoundError, YouTubeAPIError) as e:
        _raise_youtube_error(e)


@router.get("/recommendations/reference-playlist")
async def get_reference_playlist():
    from app.logic.recommendations.reference_playlist import get_reference_playlist

    return {"success": True, "referencePlaylist": get_reference_playlist()}


@router.post("/recommendations/reference-playlist")
async def set_reference_playlist(payload: ReferencePlaylistRequest):
    from app.logic.recommendations.recommendation_feed import refresh_feed
    from app.logic.recommendations.reference_playlist import save_reference_playlist

    try:
        playlist = await run_in_threadpool(
            save_reference_playlist,
            payload.url,
            limit=payload.limit,
        )
        refresh = await refresh_feed(
            max_results=25,
            mode="discover",
            replace=True,
            reason="reference_playlist_update",
        )
        return {"success": True, "referencePlaylist": playlist, "refresh": refresh}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        log.exception("Reference playlist update failed")
        raise HTTPException(status_code=500, detail=str(e)) from e


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
