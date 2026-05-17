from __future__ import annotations

import random
from typing import Any

from app.logic.api_handler.handle_yt_discovery import search_related_videos
from app.logic.recommendations.quota_tracker import can_call, record


def retrieve_related(
    graph: dict[str, Any],
    excluded: set[str],
    *,
    seed_video_id: str | None = None,
) -> list[dict[str, Any]]:
    if seed_video_id:
        seeds = [seed_video_id]
    else:
        seeds = list(graph.get("seed_video_ids") or [])
        if not seeds:
            return []
        random.shuffle(seeds)
        seeds = seeds[:10]

    out: list[dict[str, Any]] = []
    for vid in seeds:
        if not can_call(2):
            break
        try:
            rows, tok = search_related_videos(vid, 14)
        except Exception:
            continue
        record(2)
        for c in rows:
            if c.get("videoId") not in excluded:
                c["source"] = c.get("source", "related")
                c["seedVideoId"] = vid
                out.append(c)
        if tok and random.random() < 0.42 and can_call(2):
            try:
                rows2, _ = search_related_videos(vid, 10, page_token=tok)
            except Exception:
                continue
            record(2)
            for c in rows2:
                if c.get("videoId") not in excluded:
                    c["seedVideoId"] = vid
                    out.append(c)
    return out
