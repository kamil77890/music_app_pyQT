from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.db.database import session_scope
from app.db.models import UserFeedback


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


VALID_FEEDBACK = frozenset({
    "like", "dislike", "not_interested", "hide_channel",
})


def insert_feedback(
    video_id: str,
    feedback: str,
    *,
    channel_id: str | None = None,
    artist: str | None = None,
) -> None:
    if feedback not in VALID_FEEDBACK:
        raise ValueError(f"Invalid feedback: {feedback}")
    with session_scope() as session:
        session.add(
            UserFeedback(
                video_id=video_id,
                feedback=feedback,
                channel_id=channel_id,
                artist=artist,
                created_at=_utc_now(),
            )
        )


def get_negative_signals() -> dict[str, Any]:
    with session_scope() as session:
        rows = session.scalars(
            select(UserFeedback).where(
                UserFeedback.feedback.in_((
                    "dislike", "not_interested", "hide_channel",
                ))
            )
        ).all()

    hidden_channels: Counter[str] = Counter()
    disliked_videos: set[str] = set()
    disliked_artists: Counter[str] = Counter()

    for r in rows:
        if r.feedback == "hide_channel" and r.channel_id:
            hidden_channels[r.channel_id] += 1
        elif r.feedback in ("dislike", "not_interested"):
            disliked_videos.add(r.video_id)
            if r.artist:
                disliked_artists[r.artist.strip()] += 1

    return {
        "hidden_channels": list(hidden_channels.keys()),
        "disliked_video_ids": list(disliked_videos),
        "disliked_artists": [
            {"artist": a, "count": c}
            for a, c in disliked_artists.most_common(20)
        ],
    }


def get_liked_video_ids() -> set[str]:
    with session_scope() as session:
        rows = session.scalars(
            select(UserFeedback.video_id).where(UserFeedback.feedback == "like")
        ).all()
        return set(rows)
