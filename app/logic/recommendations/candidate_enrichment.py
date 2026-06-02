from __future__ import annotations

import logging
import os
from typing import Any

from app.db import candidate_repository
from app.logic.api_handler.handle_yt_discovery import enrich_videos
from app.logic.recommendations.quota_tracker import can_call, record
from app.logic.tags.universal_tags import validate_tag
from app.utils.youtube_error_handler import youtube_api_error_handler

log = logging.getLogger(__name__)

_ENRICH_TOP = int(os.environ.get("RECOMMENDATION_ENRICH_TOP", "80"))
_USE_YOUTUBE_API = os.environ.get("RECOMMENDATION_USE_YT_API", "0").lower() in {
    "1",
    "true",
    "yes",
    "on",
}


@youtube_api_error_handler
def enrich_videos_extended(video_ids: list[str]) -> dict[str, dict[str, Any]]:
    """YouTube videos.list with stats + snippet tags; uses candidate_cache."""
    if not video_ids:
        return {}
    unique = list(dict.fromkeys(video_ids))[:200]
    cached = candidate_repository.get_cached(unique)
    missing = [v for v in unique if v not in cached]

    if missing and can_call(1):
        from app.logic.api_handler.handle_yt_service import create_youtube_service

        youtube = create_youtube_service()
        fresh: dict[str, dict[str, Any]] = {}
        for i in range(0, len(missing), 50):
            chunk = missing[i : i + 50]
            resp = youtube.videos().list(
                part="snippet,contentDetails,statistics",
                id=",".join(chunk),
            ).execute()
            for item in resp.get("items", []):
                vid = item.get("id")
                if not vid:
                    continue
                stats = item.get("statistics", {})
                snippet = item.get("snippet", {})
                views = int(stats.get("viewCount", 0) or 0)
                likes = int(stats.get("likeCount", 0) or 0)
                comments = int(stats.get("commentCount", 0) or 0)
                fresh[vid] = {
                    "viewCount": views,
                    "likeCount": likes,
                    "commentCount": comments,
                    "likeRatio": round(likes / max(views, 1), 6),
                    "title": snippet.get("title", ""),
                    "artist": snippet.get("channelTitle", ""),
                    "channelId": snippet.get("channelId", ""),
                    "publishedAt": snippet.get("publishedAt", ""),
                    "categoryId": snippet.get("categoryId", ""),
                    "duration": item.get("contentDetails", {}).get("duration", ""),
                    "tags": snippet.get("tags", []) or [],
                }
        record(1)
        if fresh:
            candidate_repository.save_cached(fresh)
        cached.update(fresh)
    elif missing:
        basic = enrich_videos(missing)
        for vid, data in basic.items():
            cached.setdefault(vid, data)

    return cached


async def enrich_candidates(
    candidates: list[dict[str, Any]],
    *,
    tag_top_n: int | None = None,
) -> list[dict[str, Any]]:
    """Merge API stats into candidates; validate snippet tags."""
    if not _USE_YOUTUBE_API:
        for c in candidates:
            raw_tags = c.get("tags") or []
            c["matchedTags"] = [t for t in raw_tags if validate_tag(str(t))]
        return candidates

    n = tag_top_n or _ENRICH_TOP
    video_ids = [c["videoId"] for c in candidates if c.get("videoId")]
    enriched = enrich_videos_extended(video_ids)

    for c in candidates:
        vid = c.get("videoId")
        if not vid or vid not in enriched:
            continue
        c.update(enriched[vid])
        raw_tags = c.get("tags") or []
        c["matchedTags"] = [t for t in raw_tags if validate_tag(str(t))]

    return candidates
