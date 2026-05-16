"""One-time import from legacy JSON files into PostgreSQL."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.db.database import init_db, session_scope
from app.db.models import Notification, SeenVideo, Subscription
from app.storage import json_store

log = logging.getLogger(__name__)


def _parse_dt(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return datetime.now(timezone.utc)


def migrate_json_to_postgres() -> None:
    subs_data = json_store.read(json_store.SUBSCRIPTIONS_FILE)
    notifs_data = json_store.read(json_store.NOTIFICATIONS_FILE)
    seen_data = json_store.read(json_store.SEEN_VIDEO_IDS_FILE)

    if not subs_data and not notifs_data and not seen_data:
        return

    with session_scope() as session:
        if subs_data:
            existing = set(session.scalars(select(Subscription.channel_id)).all())
            for item in subs_data:
                cid = item.get("channelId")
                if not cid or cid in existing:
                    continue
                session.add(
                    Subscription(
                        channel_id=cid,
                        channel_title=item.get("channelTitle", ""),
                        channel_thumbnail=item.get("channelThumbnail", ""),
                        subscribed_at=_parse_dt(item.get("subscribedAt")),
                    )
                )
                existing.add(cid)

        if seen_data:
            existing_seen = set(session.scalars(select(SeenVideo.video_id)).all())
            for vid in seen_data:
                if vid and vid not in existing_seen:
                    session.add(SeenVideo(video_id=vid))
                    existing_seen.add(vid)

        if notifs_data:
            existing_ids = set(session.scalars(select(Notification.id)).all())
            for item in notifs_data:
                nid = item.get("id")
                if not nid or nid in existing_ids:
                    continue
                session.add(
                    Notification(
                        id=nid,
                        channel_id=item.get("channelId", ""),
                        channel_title=item.get("channelTitle", ""),
                        video_id=item.get("videoId", ""),
                        title=item.get("title", ""),
                        cover=item.get("cover", ""),
                        published_at=item.get("publishedAt", ""),
                        seen=bool(item.get("seen")),
                        created_at=_parse_dt(item.get("createdAt")),
                    )
                )
                vid = item.get("videoId")
                if vid and not session.get(SeenVideo, vid):
                    session.add(SeenVideo(video_id=vid))
                existing_ids.add(nid)

    log.info("JSON → PostgreSQL migration finished")
