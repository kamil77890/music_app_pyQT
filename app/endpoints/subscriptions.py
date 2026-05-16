import re
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from app.db import subscription_repository as store
from app.exceptions.youtube_errors import (
    YouTubeAccessDeniedError,
    YouTubeAPIError,
    YouTubeNotFoundError,
    YouTubeQuotaExceededError,
)
from app.logic.api_handler.handle_feed import build_subscription_feed
from app.logic.fetch_video import fetch_info

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])
notifications_router = APIRouter(prefix="/notifications", tags=["notifications"])
video_router = APIRouter(prefix="/video", tags=["video"])

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


class SubscribeBody(BaseModel):
    channelId: str
    channelTitle: str
    channelThumbnail: str


class MarkSeenBody(BaseModel):
    ids: Optional[list[str]] = None
    all: bool = False


def _raise_db_error(exc: Exception) -> None:
    raise HTTPException(status_code=500, detail={"error": str(exc)}) from exc


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


@router.post("/subscribe")
async def subscribe(body: SubscribeBody):
    try:
        store.subscribe(body.channelId, body.channelTitle, body.channelThumbnail)
        return {"success": True, "message": "Subscribed"}
    except SQLAlchemyError as e:
        _raise_db_error(e)


@router.delete("/unsubscribe/{channel_id}")
async def unsubscribe(channel_id: str):
    try:
        if not store.unsubscribe(channel_id):
            raise HTTPException(status_code=404, detail={"error": "Channel not found"})
        return {"success": True}
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        _raise_db_error(e)


@router.get("/")
async def list_subscriptions():
    try:
        return store.list_subscriptions()
    except SQLAlchemyError as e:
        _raise_db_error(e)


@router.get("/check/{channel_id}")
async def check_subscription(channel_id: str):
    try:
        return {"subscribed": store.is_subscribed(channel_id)}
    except SQLAlchemyError as e:
        _raise_db_error(e)


@router.get("/feed")
async def subscription_feed(
    max_results: int = Query(20, ge=1, le=50),
    page_token: Optional[str] = Query(None),
):
    try:
        return await run_in_threadpool(build_subscription_feed, max_results, page_token)
    except (YouTubeQuotaExceededError, YouTubeAccessDeniedError, YouTubeNotFoundError, YouTubeAPIError) as e:
        _raise_youtube_error(e)
    except SQLAlchemyError as e:
        _raise_db_error(e)


@notifications_router.get("/")
async def list_notifications(unseen_only: bool = Query(False)):
    try:
        return store.list_notifications(unseen_only=unseen_only)
    except SQLAlchemyError as e:
        _raise_db_error(e)


@notifications_router.post("/mark-seen")
async def mark_notifications_seen(body: MarkSeenBody):
    try:
        updated = store.mark_notifications_seen(ids=body.ids, mark_all=body.all)
        return {"updated": updated}
    except SQLAlchemyError as e:
        _raise_db_error(e)


@notifications_router.delete("/clear")
async def clear_seen_notifications():
    try:
        deleted = store.clear_seen_notifications()
        return {"deleted": deleted}
    except SQLAlchemyError as e:
        _raise_db_error(e)


@notifications_router.get("/count")
async def notification_count():
    try:
        return store.notification_counts()
    except SQLAlchemyError as e:
        _raise_db_error(e)


@video_router.get("/stream-url/{video_id}")
async def video_stream_url(video_id: str):
    if not VIDEO_ID_RE.fullmatch(video_id):
        return JSONResponse(
            {"error": "Invalid videoId: expected 11 characters [A-Za-z0-9_-]"},
            status_code=400,
        )
    try:
        info = fetch_info(video_id)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    chosen = next(
        (
            f
            for f in info.get("formats", [])
            if f.get("vcodec") != "none" and f.get("acodec") != "none"
        ),
        None,
    )
    if not chosen or "url" not in chosen:
        return JSONResponse({"error": "No combined video+audio format found"}, status_code=500)

    return {
        "videoId": video_id,
        "title": info.get("title"),
        "streamUrl": chosen.get("url"),
        "mimeType": chosen.get("mime_type") or "video/mp4",
        "cover": f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg",
        "expiresIn": 21600,
    }
