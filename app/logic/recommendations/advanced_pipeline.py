from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

from app.logic.api_handler.handle_yt_discovery import (
    build_expanded_discovery_queries,
    build_tag_search_queries,
    discover_from_library_top_artists,
    discover_from_library_titles,
    enrich_videos,
    run_exploratory_youtube_searches,
    search_by_query,
    search_related_videos,
)
from app.logic.recommendations.deduper import filter_duplicates
from app.logic.recommendations.playlist_service import load_playlist
from app.logic.recommendations.recommendation_scorer import rank_candidates
from app.logic.recommendations.resolver import cover_url
from app.logic.recommendations.taste_profile import build_taste_profile
from app.logic.tags.universal_tags import validate_tag

log = logging.getLogger(__name__)

ALGO_PROFILE = {"source": "youtube_algorithm", "description": "YouTube Data API + library signals + deterministic ranking"}


def _tag_search_pass(queries: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    orders = ("relevance", "viewCount", "date", "rating")
    for q in queries:
        order = random.choice(orders)
        rows, tok = search_by_query(q, 10, order=order)
        out.extend(rows)
        if tok and random.random() < 0.38:
            rows2, _ = search_by_query(q, 8, order=order, page_token=tok)
            out.extend(rows2)
    return out


def _related_pass(video_ids: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for vid in video_ids:
        rows, tok = search_related_videos(vid, 14)
        out.extend(rows)
        if tok and random.random() < 0.42:
            rows2, _ = search_related_videos(vid, 10, page_token=tok)
            out.extend(rows2)
    return out


async def run_advanced_pipeline(
    max_results: int = 10,
    seed_video_id: str | None = None,
    refresh_tags: bool = False,
) -> dict[str, Any]:
    _ = refresh_tags
    songs = load_playlist()
    if not songs:
        return {
            "profile": ALGO_PROFILE,
            "taste_profile": {},
            "data": {"songs": [], "playlist": [], "nextPageToken": None},
        }

    taste_profile = build_taste_profile()
    existing_keys, existing_ids = _library_keys(songs)

    candidates: list[dict[str, Any]] = []

    interest_parts: list[str] = []
    for t in (taste_profile.get("top_tags") or [])[:2]:
        interest_parts.append(t["tag"].replace("_", " "))
    if not interest_parts and taste_profile.get("top_artists"):
        interest_parts.append(
            (taste_profile["top_artists"][0].get("artist") or "").strip()
        )
    interest_hint = " ".join(p for p in interest_parts if p)

    excluded = set(taste_profile.get("excluded_video_ids") or []) | existing_ids
    artist_candidates = await asyncio.to_thread(
        lambda: discover_from_library_top_artists(
            taste_profile.get("top_artists", []),
            excluded,
            interest_hint=interest_hint,
            primary_popular=4,
            primary_newest=4,
            extra_artists=2,
            extra_popular=2,
            extra_newest=2,
        )
    )
    candidates.extend(artist_candidates)

    title_candidates = await asyncio.to_thread(
        lambda: discover_from_library_titles(
            taste_profile.get("top_titles", []),
            excluded,
            interest_hint=interest_hint,
            depth=6,
            popular_per=2,
            newest_per=2,
        )
    )
    candidates.extend(title_candidates)

    tag_queries = build_tag_search_queries(taste_profile, count=8)
    expanded_pool = build_expanded_discovery_queries(taste_profile, max_queries=80)

    tag_task = asyncio.to_thread(_tag_search_pass, tag_queries)
    explore_task = asyncio.to_thread(
        lambda: run_exploratory_youtube_searches(
            expanded_pool,
            excluded,
            num_queries=16,
            take_per_query=5,
        )
    )

    tag_batch, explore_batch = await asyncio.gather(tag_task, explore_task)
    candidates.extend(tag_batch)
    candidates.extend(explore_batch)

    seed_ids = _pick_seed_ids(songs, taste_profile, seed_video_id)
    related_candidates = await asyncio.to_thread(_related_pass, seed_ids)
    candidates.extend(related_candidates)

    video_ids = [c["videoId"] for c in candidates if c.get("videoId")]
    enriched = await asyncio.to_thread(enrich_videos, video_ids)
    for c in candidates:
        vid = c.get("videoId")
        if vid and vid in enriched:
            c.update(enriched[vid])
        if c.get("tags"):
            c["matchedTags"] = [t for t in c["tags"] if validate_tag(str(t))]

    ranked = rank_candidates(candidates, taste_profile, songs)

    final: list[dict[str, Any]] = []
    for c in ranked:
        if c.get("videoId") and c["videoId"] in existing_ids:
            continue
        if not c.get("videoId"):
            continue
        title = c.get("title", "")
        artist = c.get("artist", "")
        if not filter_duplicates([{"title": title, "artist": artist}], songs):
            continue
        final.append({
            "videoId": c["videoId"],
            "title": title,
            "artist": artist,
            "coverUrl": c.get("coverUrl") or cover_url(c["videoId"]),
            "url": f"https://www.youtube.com/watch?v={c['videoId']}",
            "score": c.get("score", 0),
            "matchedTags": c.get("matchedTags") or c.get("tags", []),
            "source": c.get("source", "unknown"),
            "reason": c.get("reason", ""),
        })
        if len(final) >= max_results:
            break

    return {
        "profile": ALGO_PROFILE,
        "taste_profile": taste_profile,
        "data": {
            "songs": final,
            "playlist": [],
            "nextPageToken": None,
        },
    }


async def run_youtube_recommendations(songs: list[dict[str, Any]], max_results: int):
    """
    Same engine as /recommendations/advanced; uses live playlist via load_playlist internally.
    """
    _ = songs
    result = await run_advanced_pipeline(max_results=max_results)
    return result["profile"], result["data"]["songs"]


def _library_keys(songs: list[dict[str, Any]]) -> tuple[set[str], set[str]]:
    from app.utils.music_utils import song_key

    keys: set[str] = set()
    ids: set[str] = set()
    for s in songs:
        keys.add(song_key(s))
        vid = s.get("videoId") or s.get("id")
        if vid:
            ids.add(str(vid))
    return keys, ids


def _pick_seed_ids(
    songs: list[dict[str, Any]],
    profile: dict[str, Any],
    seed_video_id: str | None,
) -> list[str]:
    if seed_video_id:
        return [seed_video_id]
    ids: list[str] = []
    for s in songs:
        vid = s.get("videoId") or s.get("id")
        if vid:
            ids.append(str(vid))
    random.shuffle(ids)
    return ids[:10] if ids else []
