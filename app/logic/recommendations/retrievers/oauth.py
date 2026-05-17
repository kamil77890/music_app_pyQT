from __future__ import annotations

from typing import Any

from app.db import oauth_repository
from app.logic.api_handler.handle_yt_discovery import search_music_videos_simple
from app.logic.recommendations.music_filter import is_likely_music
from app.logic.recommendations.quota_tracker import can_call, record


def retrieve_oauth_music(
    graph: dict[str, Any],
    excluded: set[str],
) -> list[dict[str, Any]]:
    """Music-only OAuth likes + similar searches (not raw gaming uploads)."""
    if not oauth_repository.is_connected():
        return []

    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in graph.get("music_oauth_items") or []:
        vid = item.get("video_id")
        if not vid or vid in excluded or vid in seen:
            continue
        title = item.get("title") or ""
        if not is_likely_music(title, channel_title=item.get("channel_title", ""), min_score=0.38):
            continue
        seen.add(vid)
        out.append({
            "videoId": vid,
            "title": title,
            "artist": item.get("channel_title", ""),
            "source": "oauth_music_liked",
            "reason": "From your YouTube likes (music)",
        })

    for item in (graph.get("music_oauth_items") or [])[:8]:
        title = (item.get("title") or "").strip()
        channel = (item.get("channel_title") or "").strip()
        if not title or not can_call(1):
            break
        q_parts = []
        if channel and channel.lower() not in ("kamil7777",):
            q_parts.append(f'"{channel}"')
        short = title[:50].replace('"', "")
        if short:
            q_parts.append(short)
        q_parts.append("music")
        q = " ".join(q_parts)
        batch = search_music_videos_simple(q, order="relevance", max_results=6)
        record(1)
        for c in batch:
            vid = c.get("videoId")
            if not vid or vid in excluded or vid in seen:
                continue
            if not is_likely_music(c.get("title", ""), channel_title=c.get("artist", "")):
                continue
            seen.add(vid)
            c["source"] = "oauth_similar"
            c["reason"] = f"Similar to your liked: {short[:35]}"
            out.append(c)

    return out[:25]
