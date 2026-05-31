from __future__ import annotations

import re
from typing import Any

from app.logic.recommendations.music_filter import is_likely_music, is_short

_EXPLORE_SOURCES = frozenset({
    "yt_explore", "gemini_query", "tag_search", "music_search", "reference_playlist",
})

_MIX_PATTERNS = re.compile(
    r"\b(mix|playlist|compilation|best of|24/7|hour|non.?stop)\b",
    re.I,
)


def _is_mix_or_compilation(title: str) -> bool:
    return bool(_MIX_PATTERNS.search(title or ""))


def apply_diversity(
    ranked: list[dict[str, Any]],
    graph: dict[str, Any],
    *,
    max_results: int,
    max_per_channel: int = 2,
    explore_slots: int = 2,
) -> list[dict[str, Any]]:
    hidden = set(graph.get("negative", {}).get("hidden_channels", []))
    disliked = set(graph.get("negative", {}).get("disliked_video_ids", []))
    negative_artists = {
        e.get("artist", "").lower()
        for e in graph.get("negative", {}).get("disliked_artists", [])
    }

    channel_count: dict[str, int] = {}
    tag_seen: set[str] = set()
    final: list[dict[str, Any]] = []
    explore_added = 0
    explore_pool = [r for r in ranked if r.get("source") in _EXPLORE_SOURCES]

    def channel_key(row: dict[str, Any]) -> str:
        return (row.get("channelId") or row.get("artist") or "").lower()

    def accept(row: dict[str, Any], *, force_explore: bool = False) -> bool:
        vid = row.get("videoId")
        if not vid or vid in disliked:
            return False
        if is_short(title=row.get("title", "")):
            return False
        cid = row.get("channelId") or ""
        if cid and cid in hidden:
            return False
        ch = channel_key(row)
        artist_l = (row.get("artist") or "").lower()
        if artist_l in negative_artists:
            return False
        if _is_mix_or_compilation(row.get("title", "")):
            return False
        if not is_likely_music(
            row.get("title", ""),
            category_id=row.get("categoryId"),
            tags=row.get("matchedTags") or row.get("tags"),
            channel_title=row.get("artist", ""),
            min_score=0.38,
        ):
            return False
        if ch and channel_count.get(ch, 0) >= max_per_channel and not force_explore:
            return False
        tags = set(row.get("matchedTags") or row.get("tags") or [])
        if tags and tags.issubset(tag_seen) and len(final) >= 3 and not force_explore:
            overlap = len(tags & tag_seen) / max(len(tags), 1)
            if overlap > 0.85:
                return False
        return True

    for row in ranked:
        if len(final) >= max_results:
            break
        if accept(row):
            ch = channel_key(row)
            if ch:
                channel_count[ch] = channel_count.get(ch, 0) + 1
            tag_seen |= set(row.get("matchedTags") or [])
            final.append(row)

    while explore_added < explore_slots and len(final) < max_results and explore_pool:
        for row in explore_pool:
            if row in final:
                continue
            if accept(row, force_explore=True):
                final.append(row)
                explore_added += 1
                break
        else:
            break

    return final[:max_results]
