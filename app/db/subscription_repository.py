from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.database import session_scope
from app.db.models import Notification, SeenVideo, Subscription


class DatabaseError(Exception):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _sub_to_dict(row: Subscription) -> dict[str, Any]:
    return {
        "channelId": row.channel_id,
        "channelTitle": row.channel_title,
        "channelThumbnail": row.channel_thumbnail,
        "subscribedAt": row.subscribed_at.isoformat(),
    }


def _notif_to_dict(row: Notification) -> dict[str, Any]:
    return {
        "id": row.id,
        "channelId": row.channel_id,
        "channelTitle": row.channel_title,
        "videoId": row.video_id,
        "title": row.title,
        "cover": row.cover,
        "publishedAt": row.published_at,
        "seen": row.seen,
        "createdAt": row.created_at.isoformat(),
    }


def list_subscriptions() -> list[dict[str, Any]]:
    with session_scope() as session:
        rows = session.scalars(
            select(Subscription).order_by(Subscription.subscribed_at.desc())
        ).all()
        return [_sub_to_dict(r) for r in rows]


def subscribe(channel_id: str, channel_title: str, channel_thumbnail: str) -> bool:
    """Returns True if a new row was created."""
    with session_scope() as session:
        if session.get(Subscription, channel_id):
            return False
        session.add(
            Subscription(
                channel_id=channel_id,
                channel_title=channel_title,
                channel_thumbnail=channel_thumbnail,
                subscribed_at=_utc_now(),
            )
        )
        return True


def unsubscribe(channel_id: str) -> bool:
    """Returns True if a row was deleted."""
    with session_scope() as session:
        row = session.get(Subscription, channel_id)
        if not row:
            return False
        session.delete(row)
        return True


def is_subscribed(channel_id: str) -> bool:
    with session_scope() as session:
        return session.get(Subscription, channel_id) is not None


def process_new_videos(videos: list[dict[str, Any]]) -> int:
    with session_scope() as session:
        return _process_new_videos(session, videos)


def _process_new_videos(session: Session, videos: list[dict[str, Any]]) -> int:
    new_count = 0
    now = _utc_now()

    for video in videos:
        video_id = video.get("videoId")
        if not video_id or session.get(SeenVideo, video_id):
            continue
        session.add(SeenVideo(video_id=video_id))
        session.add(
            Notification(
                id=str(uuid4()),
                channel_id=video.get("channelId", ""),
                channel_title=video.get("channelTitle", ""),
                video_id=video_id,
                title=video.get("title", ""),
                cover=video.get(
                    "cover", f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"
                ),
                published_at=video.get("publishedAt", ""),
                seen=False,
                created_at=now,
            )
        )
        new_count += 1

    return new_count


def list_notifications(unseen_only: bool = False) -> list[dict[str, Any]]:
    with session_scope() as session:
        stmt = select(Notification).order_by(Notification.created_at.desc())
        if unseen_only:
            stmt = stmt.where(Notification.seen.is_(False))
        rows = session.scalars(stmt).all()
        return [_notif_to_dict(r) for r in rows]


def mark_notifications_seen(ids: list[str] | None = None, mark_all: bool = False) -> int:
    with session_scope() as session:
        if mark_all:
            result = session.execute(
                update(Notification)
                .where(Notification.seen.is_(False))
                .values(seen=True)
            )
        elif ids:
            result = session.execute(
                update(Notification)
                .where(Notification.id.in_(ids), Notification.seen.is_(False))
                .values(seen=True)
            )
        else:
            return 0
        return result.rowcount


def clear_seen_notifications() -> int:
    with session_scope() as session:
        result = session.execute(
            delete(Notification).where(Notification.seen.is_(True))
        )
        return result.rowcount


def notification_counts() -> dict[str, int]:
    with session_scope() as session:
        total = session.scalar(select(func.count()).select_from(Notification)) or 0
        unseen = (
            session.scalar(
                select(func.count())
                .select_from(Notification)
                .where(Notification.seen.is_(False))
            )
            or 0
        )
        return {"unseen": unseen, "total": total}
