from fastapi import APIRouter, HTTPException

from app.db import event_repository, feedback_repository
from app.models.event_models import (
    EventsBatchIn,
    FeedbackIn,
    ImpressionClickIn,
    ImpressionsIn,
)

router = APIRouter(tags=["Events"])


@router.post("/events/batch")
async def post_events_batch(body: EventsBatchIn):
    """
    Batch listening events from the client (play, skip, progress, complete).

    Send up to 50 events per request. Include session_id to correlate a playback session.
    """
    if not body.events:
        return {"success": True, "inserted": 0}
    payload = [e.model_dump() for e in body.events]
    try:
        n = event_repository.insert_listening_events(payload)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"success": True, "inserted": n}


@router.post("/feedback")
async def post_feedback(body: FeedbackIn):
    """Explicit feedback: like, dislike, not_interested, hide_channel."""
    try:
        feedback_repository.insert_feedback(
            body.video_id,
            body.feedback,
            channel_id=body.channel_id,
            artist=body.artist,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"success": True}


@router.post("/recommendations/impression")
async def post_recommendation_impression(body: ImpressionsIn):
    """Record which recommended videos were shown in a feed request."""
    if not body.items:
        return {"success": True, "inserted": 0}
    payload = [i.model_dump() for i in body.items]
    n = event_repository.insert_impressions(body.request_id, payload)
    return {"success": True, "inserted": n}


@router.post("/recommendations/click")
async def post_recommendation_click(body: ImpressionClickIn):
    """Mark a previously impressed recommendation as clicked."""
    ok = event_repository.mark_impression_clicked(body.request_id, body.video_id)
    if not ok:
        raise HTTPException(404, "impression not found for request_id/video_id")
    return {"success": True}
