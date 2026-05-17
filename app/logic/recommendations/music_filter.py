from __future__ import annotations

import re
from typing import Any

# YouTube category 10 = Music
_MUSIC_CATEGORY = "10"

_NON_MUSIC_TITLE = re.compile(
    r"\b("
    r"10\s*tier|tier\s*list|smp|minecraft|paczek|dota|csgo|valorant|"
    r"fortnite|roblox|wyjaśnienie|totalne|unstable|civil\s*war|"
    r"podcast|vlog|tutorial|gameplay|let'?s\s*play|"
    r"otwórz|zobacz\s+jak|addressing\s+the"
    r")\b",
    re.I,
)

_MUSIC_TITLE = re.compile(
    r"\b("
    r"nightcore|lyrics|official|audio|mv\b|amv|cover|remix|ft\.|feat\.|"
    r"song|music|ost\b|soundtrack|album|single|ep\b|"
    r"maneskin|linkin\s*park|anime\s*mix"
    r")\b",
    re.I,
)

_TOPIC_MUSIC = re.compile(
    r"\b(music|pop|rock|electronic|nightcore|anime)\b",
    re.I,
)


def music_likelihood(
    title: str = "",
    *,
    category_id: str | None = None,
    tags: list[str] | None = None,
    channel_title: str = "",
) -> float:
    """0..1 — how likely this is a music video."""
    t = title or ""
    if category_id == _MUSIC_CATEGORY:
        return 0.95
    if _NON_MUSIC_TITLE.search(t):
        return 0.05
    score = 0.35
    if _MUSIC_TITLE.search(t):
        score += 0.45
    if tags:
        tag_str = " ".join(str(x) for x in tags).lower()
        if _TOPIC_MUSIC.search(tag_str):
            score += 0.15
    ch = (channel_title or "").lower()
    if any(x in ch for x in ("topic", "vevo", "records", "nightcore", "- topic")):
        score += 0.2
    if "official" in t.lower() and ("audio" in t.lower() or "video" in t.lower()):
        score += 0.15
    return min(1.0, score)


def is_likely_music(
    title: str = "",
    *,
    category_id: str | None = None,
    tags: list[str] | None = None,
    channel_title: str = "",
    min_score: float = 0.42,
) -> bool:
    return music_likelihood(
        title,
        category_id=category_id,
        tags=tags,
        channel_title=channel_title,
    ) >= min_score


def filter_music_candidates(
    candidates: list[dict[str, Any]],
    *,
    min_score: float = 0.42,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for c in candidates:
        if is_likely_music(
            c.get("title", ""),
            category_id=c.get("categoryId"),
            tags=c.get("matchedTags") or c.get("tags"),
            channel_title=c.get("artist", ""),
            min_score=min_score,
        ):
            c = dict(c)
            c["musicScore"] = round(
                music_likelihood(
                    c.get("title", ""),
                    category_id=c.get("categoryId"),
                    tags=c.get("matchedTags") or c.get("tags"),
                    channel_title=c.get("artist", ""),
                ),
                3,
            )
            out.append(c)
    return out
