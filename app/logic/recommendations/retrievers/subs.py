from __future__ import annotations

from typing import Any

from app.db import subscription_repository
from app.logic.api_handler.handle_feed import fetch_channel_videos
from app.logic.recommendations.quota_tracker import can_call, record


def retrieve_subscription_candidates(
    graph: dict[str, Any],
    excluded: set[str],
) -> list[dict[str, Any]]:
    subs = subscription_repository.list_subscriptions()
    if not subs or not can_call(2):
        return []
    out: list[dict[str, Any]] = []
    channel_weights = graph.get("channel_weights") or {}
    ordered = sorted(
        subs,
        key=lambda s: channel_weights.get(s.get("channelId", ""), 0),
        reverse=True,
    )
    for sub in ordered[:5]:
        cid = sub.get("channelId")
        if not cid or not can_call(1):
            break
        try:
            videos = fetch_channel_videos(cid, max_results=3)
        except Exception:
            continue
        record(1)
        for v in videos:
            vid = v.get("videoId")
            if not vid or vid in excluded:
                continue
            out.append({
                "videoId": vid,
                "title": v.get("title", ""),
                "artist": v.get("channelTitle", sub.get("channelTitle", "")),
                "channelId": cid,
                "publishedAt": v.get("publishedAt", ""),
                "source": "subscription_feed",
                "reason": f"New from subscribed channel {sub.get('channelTitle', '')}",
            })
    return out


def retrieve_notification_candidates(
    excluded: set[str],
) -> list[dict[str, Any]]:
    notifs = subscription_repository.list_notifications(unseen_only=True)
    out: list[dict[str, Any]] = []
    for n in notifs[:15]:
        vid = n.get("videoId")
        if not vid or vid in excluded:
            continue
        out.append({
            "videoId": vid,
            "title": n.get("title", ""),
            "artist": n.get("channelTitle", ""),
            "channelId": n.get("channelId"),
            "publishedAt": n.get("publishedAt", ""),
            "source": "notification",
            "reason": "Unseen subscription notification",
        })
    return out
