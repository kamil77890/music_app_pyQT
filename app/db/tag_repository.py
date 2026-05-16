from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, func, select

from app.db.database import session_scope
from app.db.models import SongTag, TasteProfileCache


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_tags(video_id: str) -> list[dict[str, Any]]:
    with session_scope() as session:
        rows = session.scalars(
            select(SongTag).where(SongTag.video_id == video_id)
        ).all()
        return [
            {
                "tag": r.tag,
                "dimension": r.dimension,
                "confidence": r.confidence,
                "source": r.source,
            }
            for r in rows
        ]


def has_tags(video_id: str) -> bool:
    with session_scope() as session:
        count = session.scalar(
            select(func.count()).select_from(SongTag).where(SongTag.video_id == video_id)
        )
        return (count or 0) > 0


def set_tags(video_id: str, tags: list[dict[str, Any]]) -> None:
    with session_scope() as session:
        session.execute(delete(SongTag).where(SongTag.video_id == video_id))
        now = _utc_now()
        for t in tags:
            session.add(
                SongTag(
                    video_id=video_id,
                    tag=t["tag"],
                    dimension=t["dimension"],
                    confidence=t.get("confidence", 0.7),
                    source=t.get("source", "ai"),
                    updated_at=now,
                )
            )


def bulk_upsert(video_id: str, tags: list[dict[str, Any]]) -> None:
    set_tags(video_id, tags)


def get_tagged_video_ids() -> set[str]:
    with session_scope() as session:
        rows = session.scalars(select(SongTag.video_id).distinct()).all()
        return set(rows)


def get_library_tag_histogram() -> dict[str, float]:
    with session_scope() as session:
        rows = session.execute(
            select(SongTag.tag, func.sum(SongTag.confidence))
            .group_by(SongTag.tag)
        ).all()
    if not rows:
        return {}
    total = sum(w for _, w in rows) or 1.0
    return {tag: float(weight) / total for tag, weight in rows}


def get_tag_counts_by_dimension() -> dict[str, dict[str, float]]:
    with session_scope() as session:
        rows = session.scalars(select(SongTag)).all()
        triples = [(r.dimension, r.tag, r.confidence) for r in rows]
    by_dim: dict[str, Counter[str]] = {}
    for dim, tag, conf in triples:
        by_dim.setdefault(dim, Counter())[tag] += conf
    result: dict[str, dict[str, float]] = {}
    for dim, counter in by_dim.items():
        total = sum(counter.values()) or 1.0
        result[dim] = {tag: count / total for tag, count in counter.items()}
    return result


def get_cached_taste_profile(library_hash: str) -> dict[str, Any] | None:
    with session_scope() as session:
        row = session.get(TasteProfileCache, 1)
        if not row or row.library_hash != library_hash:
            return None
        return json.loads(row.profile_json)


def save_taste_profile(library_hash: str, profile: dict[str, Any]) -> None:
    with session_scope() as session:
        row = session.get(TasteProfileCache, 1)
        payload = json.dumps(profile, ensure_ascii=False)
        now = _utc_now()
        if row:
            row.profile_json = payload
            row.library_hash = library_hash
            row.updated_at = now
        else:
            session.add(
                TasteProfileCache(
                    id=1,
                    profile_json=payload,
                    library_hash=library_hash,
                    updated_at=now,
                )
            )
