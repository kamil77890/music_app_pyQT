from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, select

from app.db.database import session_scope
from app.db.models import CandidateCache


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _ttl_hours() -> int:
    return int(os.environ.get("RECOMMENDATION_CACHE_TTL_HOURS", "24"))


def get_cached(video_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not video_ids:
        return {}
    cutoff = _utc_now() - timedelta(hours=_ttl_hours())
    result: dict[str, dict[str, Any]] = {}
    with session_scope() as session:
        rows = session.scalars(
            select(CandidateCache).where(CandidateCache.video_id.in_(video_ids))
        ).all()
        for r in rows:
            if _as_utc(r.fetched_at) >= cutoff:
                try:
                    result[r.video_id] = json.loads(r.payload_json)
                except json.JSONDecodeError:
                    pass
    return result


def save_cached(items: dict[str, dict[str, Any]]) -> None:
    if not items:
        return
    now = _utc_now()
    with session_scope() as session:
        for vid, payload in items.items():
            row = session.get(CandidateCache, vid)
            blob = json.dumps(payload, ensure_ascii=False)
            if row:
                row.payload_json = blob
                row.fetched_at = now
            else:
                session.add(
                    CandidateCache(
                        video_id=vid,
                        payload_json=blob,
                        fetched_at=now,
                    )
                )


def prune_expired() -> int:
    cutoff = _utc_now() - timedelta(hours=_ttl_hours() * 2)
    with session_scope() as session:
        result = session.execute(
            delete(CandidateCache).where(CandidateCache.fetched_at < cutoff)
        )
        return result.rowcount or 0
