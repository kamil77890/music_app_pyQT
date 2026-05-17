from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select

from app.db.database import session_scope
from app.db.models import ListeningEvent, RecommendationImpression


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def insert_listening_events(events: list[dict[str, Any]]) -> int:
    if not events:
        return 0
    now = _utc_now()
    with session_scope() as session:
        for e in events:
            session.add(
                ListeningEvent(
                    video_id=e["video_id"],
                    event_type=e["event_type"],
                    position_sec=e.get("position_sec"),
                    duration_sec=e.get("duration_sec"),
                    session_id=e.get("session_id"),
                    channel_id=e.get("channel_id"),
                    artist=e.get("artist"),
                    title=e.get("title"),
                    created_at=e.get("created_at") or now,
                )
            )
        return len(events)


def insert_impressions(
    request_id: str,
    items: list[dict[str, Any]],
) -> int:
    if not items:
        return 0
    now = _utc_now()
    with session_scope() as session:
        for item in items:
            session.add(
                RecommendationImpression(
                    request_id=request_id,
                    video_id=item["video_id"],
                    position=int(item.get("position", 0)),
                    clicked=bool(item.get("clicked", False)),
                    dismissed=bool(item.get("dismissed", False)),
                    created_at=now,
                )
            )
        return len(items)


def mark_impression_clicked(request_id: str, video_id: str) -> bool:
    with session_scope() as session:
        row = session.scalar(
            select(RecommendationImpression)
            .where(
                RecommendationImpression.request_id == request_id,
                RecommendationImpression.video_id == video_id,
            )
            .order_by(RecommendationImpression.created_at.desc())
            .limit(1)
        )
        if not row:
            return False
        row.clicked = True
        return True


def get_behavioral_aggregates(*, days: int = 90) -> dict[str, Any]:
    """Aggregate play/skip/complete signals for taste graph."""
    cutoff = _utc_now() - timedelta(days=days)
    with session_scope() as session:
        orm_rows = session.scalars(
            select(ListeningEvent).where(ListeningEvent.created_at >= cutoff)
        ).all()
        rows = [
            {
                "video_id": r.video_id,
                "event_type": r.event_type,
                "position_sec": r.position_sec,
                "duration_sec": r.duration_sec,
                "session_id": r.session_id,
                "channel_id": r.channel_id,
                "artist": r.artist,
            }
            for r in orm_rows
        ]

    video_plays: Counter[str] = Counter()
    video_completes: Counter[str] = Counter()
    video_skips: Counter[str] = Counter()
    channel_plays: Counter[str] = Counter()
    artist_plays: Counter[str] = Counter()
    listen_ratios: dict[str, list[float]] = defaultdict(list)
    replay_videos: Counter[str] = Counter()

    for r in rows:
        vid = r["video_id"]
        et = r["event_type"]
        if et in ("play", "start"):
            video_plays[vid] += 1
            if r.get("channel_id"):
                channel_plays[r["channel_id"]] += 1
            if r.get("artist"):
                artist_plays[r["artist"].strip()] += 1
        elif et == "complete":
            video_completes[vid] += 1
        elif et == "skip":
            video_skips[vid] += 1
        pos = r.get("position_sec")
        dur = r.get("duration_sec")
        if pos is not None and dur and dur > 0:
            listen_ratios[vid].append(min(1.0, pos / dur))

    top_videos = [
        {
            "video_id": vid,
            "play_count": video_plays[vid],
            "complete_count": video_completes[vid],
            "skip_count": video_skips[vid],
            "avg_listen_ratio": round(
                sum(listen_ratios[vid]) / len(listen_ratios[vid]), 3
            )
            if listen_ratios[vid]
            else 0.0,
        }
        for vid, _ in video_plays.most_common(50)
    ]

    return {
        "top_videos": top_videos,
        "top_channels": [
            {"channel_id": c, "play_count": n}
            for c, n in channel_plays.most_common(20)
        ],
        "top_artists": [
            {"artist": a, "play_count": n}
            for a, n in artist_plays.most_common(20)
        ],
        "total_events": len(rows),
        "skip_rate": round(
            sum(video_skips.values()) / max(1, sum(video_plays.values())), 3
        ),
    }


def get_top_seed_video_ids(*, limit: int = 10) -> list[str]:
    """Videos to use as related-video seeds (by play count + completion)."""
    agg = get_behavioral_aggregates()
    scored: list[tuple[float, str]] = []
    for v in agg.get("top_videos", []):
        vid = v.get("video_id")
        if not vid:
            continue
        score = (
            v.get("play_count", 0) * 2
            + v.get("complete_count", 0) * 3
            - v.get("skip_count", 0)
        )
        if v.get("avg_listen_ratio", 0) > 0.7:
            score += 2
        scored.append((score, vid))
    scored.sort(reverse=True)
    return [vid for _, vid in scored[:limit]]


def events_hash_suffix() -> str:
    """Short suffix for taste profile cache invalidation."""
    with session_scope() as session:
        latest = session.scalar(
            select(func.max(ListeningEvent.created_at))
        )
        count = session.scalar(select(func.count()).select_from(ListeningEvent)) or 0
    if not latest:
        return "ev0"
    bucket = int(latest.timestamp()) // 300
    return f"ev{count}:{bucket}"
