from __future__ import annotations

import asyncio
import logging
import os
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Literal

from app.logic.recommendations.candidate_enrichment import enrich_candidates
from app.logic.recommendations.music_filter import filter_music_candidates
from app.logic.recommendations.deduper import filter_duplicates
from app.logic.recommendations.diversity_mixer import apply_diversity
from app.logic.recommendations.playlist_service import load_playlist
from app.logic.recommendations.quota_tracker import (
    SEARCH_UNITS,
    max_calls,
    remaining as remaining_units,
    reset,
    used as quota_used,
)
from app.logic.recommendations.recommendation_scorer import rank_candidates
from app.logic.recommendations.resolver import cover_url
from app.logic.recommendations.retrievers import (
    retrieve_album_candidates,
    retrieve_explore,
    retrieve_gemini_queries,
    retrieve_library_artists,
    retrieve_library_titles,
    retrieve_notification_candidates,
    retrieve_oauth_music,
    retrieve_related,
    retrieve_subscription_candidates,
    retrieve_tag_queries,
)
from app.logic.recommendations.retrievers.ytdlp_search import retrieve_ytdlp_candidates
from app.exceptions.youtube_errors import YouTubeQuotaExceededError
from app.logic.recommendations.user_taste_graph import build_user_taste_graph

log = logging.getLogger(__name__)


Mode = Literal["focus", "discover", "fresh"]

ALGO_PROFILE = {
    "source": "youtube_multi_retriever",
    "description": "Multi-source YouTube recommendations with behavioral taste graph",
}

_CONFIDENCE_THRESHOLD = float(
    os.environ.get("RECOMMENDATION_CONFIDENCE_THRESHOLD", "0.85")
)
_USE_YOUTUBE_API = os.environ.get("RECOMMENDATION_USE_YT_API", "0").lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def _compute_confidence(ranked: list[dict[str, Any]], max_results: int) -> float:
    """Confidence in the taste-matched recommendations (0..1).

    Blends the average score of the top results (how strong the matches are)
    with coverage (whether we found enough candidates to choose from).
    """
    if not ranked:
        return 0.0
    top = sorted((float(r.get("score", 0)) for r in ranked), reverse=True)[:max_results]
    if not top:
        return 0.0
    avg = sum(top) / len(top)
    coverage = min(1.0, len(ranked) / max(1, max_results * 2))
    return round((avg / 100.0) * 0.8 + coverage * 0.2, 3)


def _subscribed_channel_ids() -> set[str]:
    try:
        from app.db import subscription_repository
        return {
            s.get("channelId")
            for s in subscription_repository.list_subscriptions()
            if s.get("channelId")
        }
    except Exception:
        return set()


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


def _interest_hint(graph: dict[str, Any]) -> str:
    parts: list[str] = []
    for t in (graph.get("top_tags") or [])[:3]:
        parts.append(t["tag"].replace("_", " "))
    for a in graph.get("top_artists") or []:
        if a.get("from_library") and a.get("song_count", 0) > 0:
            parts.append((a.get("artist") or "").strip())
            break
    return " ".join(p for p in parts if p)


def _apply_mode(graph: dict[str, Any], mode: Mode) -> dict[str, Any]:
    g = dict(graph)
    if mode == "discover":
        g["exploration_budget"] = min(0.55, float(g.get("exploration_budget", 0.2)) + 0.25)
    elif mode == "fresh":
        g["exploration_budget"] = min(0.5, float(g.get("exploration_budget", 0.2)) + 0.15)
        eras = g.get("top_eras") or []
        # Prefer the user's newest era from their own library instead of a fixed year.
        newest = _newest_era(eras)
        if newest:
            g["top_eras"] = [{"era": newest, "weight": 1.0}] + [
                e for e in eras if e.get("era") != newest
            ][:4]
    return g


def _newest_era(eras: list[dict[str, Any]]) -> str | None:
    """Most recent era label present in the user's library (e.g. '2020s')."""
    labels = [str(e.get("era") or "") for e in eras if e.get("era")]
    decade_like = [l for l in labels if l[:4].isdigit()]
    if decade_like:
        return max(decade_like, key=lambda l: l[:4])
    return labels[0] if labels else None


async def _maybe_llm_rerank(
    ranked: list[dict[str, Any]],
    graph: dict[str, Any],
    songs: list[dict[str, Any]],
    *,
    use_llm: bool,
    max_results: int,
) -> list[dict[str, Any]]:
    if not use_llm or len(ranked) < 3:
        return ranked
    try:
        from app.logic.recommendations.gemini_advanced import ask_gemini_advanced

        _, gemini_recs = await ask_gemini_advanced(graph, songs, max_results)
        if not gemini_recs:
            return ranked
        gemini_keys = {
            ((r.get("artist") or "").lower(), (r.get("title") or "").lower())
            for r in gemini_recs
        }
        boosted: list[dict[str, Any]] = []
        rest: list[dict[str, Any]] = []
        for row in ranked:
            key = ((row.get("artist") or "").lower(), (row.get("title") or "").lower())
            if key in gemini_keys:
                row = dict(row)
                row["score"] = min(100.0, row.get("score", 0) + 8)
                row["reason"] = row.get("reason") or "Gemini taste match"
                boosted.append(row)
            else:
                rest.append(row)
        boosted.sort(key=lambda x: -x.get("score", 0))
        return boosted + rest
    except Exception:
        log.exception("LLM rerank failed")
        return ranked


async def run_recommendation_orchestrator(
    max_results: int = 10,
    *,
    seed_video_id: str | None = None,
    mode: Mode = "focus",
    use_llm_rerank: bool = False,
    max_per_channel: int = 2,
    debug_scores: bool = False,
) -> dict[str, Any]:
    request_id = str(uuid.uuid4())
    reset()
    songs = load_playlist()
    if not songs:
        return {
            "request_id": request_id,
            "profile": ALGO_PROFILE,
            "taste_profile": {},
            "data": {"songs": [], "playlist": [], "nextPageToken": None},
            "quota_used": 0,
            "quota_max": max_calls(),
        }

    graph = _apply_mode(build_user_taste_graph(), mode)
    _, existing_ids = _library_keys(songs)
    excluded = set(graph.get("excluded_video_ids") or []) | existing_ids
    hint = _interest_hint(graph)

    candidates: list[dict[str, Any]] = []

    library_artists = [
        a for a in (graph.get("top_artists") or [])
        if a.get("from_library") and a.get("song_count", 0) > 0
    ]
    graph_for_discovery = dict(graph)
    graph_for_discovery["top_artists"] = library_artists or graph.get("top_artists", [])

    def _run_retriever(name: str, fn) -> list[dict[str, Any]]:
        try:
            return list(fn())
        except YouTubeQuotaExceededError:
            log.warning("YouTube quota hit at %s — using partial candidates", name)
            return []
        except Exception:
            log.exception("Retriever %s failed", name)
            return []

    def _run_wave(jobs: list[tuple[str, Any]]) -> list[dict[str, Any]]:
        """Run independent retrievers concurrently; the thread-safe quota
        tracker caps real API spend across them."""
        out: list[dict[str, Any]] = []
        if not jobs:
            return out
        with ThreadPoolExecutor(max_workers=min(len(jobs), 6)) as pool:
            futures = {pool.submit(_run_retriever, name, fn): name for name, fn in jobs}
            for fut in as_completed(futures):
                out.extend(fut.result())
        return out

    def sync_retrievers() -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []

        # Wave 1 — high-signal, library/subscription sources (run in parallel).
        core_jobs = [
            ("oauth_music", lambda: retrieve_oauth_music(graph, excluded)),
            ("library_artists", lambda: retrieve_library_artists(
                graph_for_discovery, excluded, interest_hint=hint)),
            ("library_titles", lambda: retrieve_library_titles(
                graph, excluded, interest_hint=hint)),
            ("tag_queries", lambda: retrieve_tag_queries(graph, excluded)),
            ("related", lambda: retrieve_related(
                graph, excluded, seed_video_id=seed_video_id)),
            ("subscriptions", lambda: retrieve_subscription_candidates(graph, excluded)),
            ("notifications", lambda: retrieve_notification_candidates(excluded)),
        ]
        out.extend(_run_wave(core_jobs))

        # Wave 2 — broad exploration only if budget remains.
        if remaining_units() > SEARCH_UNITS * 3:
            explore_n = 14 if mode == "discover" else 8
            explore_jobs = [
                ("explore", lambda: retrieve_explore(graph, excluded, num_queries=explore_n)),
                ("albums", lambda: retrieve_album_candidates(graph_for_discovery, excluded)),
            ]
            out.extend(_run_wave(explore_jobs))
        return out

    if _USE_YOUTUBE_API:
        sync_batch = await asyncio.to_thread(sync_retrievers)
    else:
        sync_batch = await asyncio.to_thread(
            retrieve_ytdlp_candidates,
            graph,
            excluded,
            songs,
            seed_video_id=seed_video_id,
            mode=mode,
            max_results=max_results * 8,
            interest_hint=hint,
        )
    candidates.extend(sync_batch)

    # Gemini-generated search queries cost LLM tokens on every request, so they
    # only run when the caller explicitly opts into LLM assistance.
    if use_llm_rerank and _USE_YOUTUBE_API:
        gemini_batch = await retrieve_gemini_queries(graph, excluded)
        candidates.extend(gemini_batch)

    candidates = await enrich_candidates(candidates)
    known_artists = {
        (a.get("artist") or "").strip().lower()
        for a in (graph.get("top_artists") or [])
        if a.get("from_library") and (a.get("artist") or "").strip()
    }
    candidates = filter_music_candidates(
        candidates, min_score=0.4, known_artists=known_artists
    )

    ranked = rank_candidates(candidates, graph, songs)
    ranked = await _maybe_llm_rerank(
        ranked, graph, songs, use_llm=use_llm_rerank, max_results=max_results
    )

    explore_slots = 3 if mode == "discover" else 2
    diverse = apply_diversity(
        ranked,
        graph,
        max_results=max_results * 2,
        max_per_channel=max_per_channel,
        explore_slots=explore_slots,
    )

    subscribed_ids = _subscribed_channel_ids()
    library_artists_lc = {
        (a.get("artist") or "").lower()
        for a in (graph.get("top_artists") or [])
        if a.get("from_library")
    }

    def _is_new_channel(c: dict[str, Any]) -> bool:
        cid = c.get("channelId")
        artist_lc = (c.get("artist") or "").lower()
        return bool(cid) and cid not in subscribed_ids and artist_lc not in library_artists_lc

    def _to_item(c: dict[str, Any]) -> dict[str, Any]:
        item: dict[str, Any] = {
            "videoId": c["videoId"],
            "title": c.get("title", ""),
            "artist": c.get("artist", ""),
            "coverUrl": c.get("coverUrl") or cover_url(c["videoId"]),
            "url": f"https://www.youtube.com/watch?v={c['videoId']}",
            "score": c.get("score", 0),
            "matchedTags": c.get("matchedTags") or c.get("tags", []),
            "source": c.get("source", "unknown"),
            "reason": c.get("reason", ""),
            "isNewChannel": _is_new_channel(c),
            "publishedAt": c.get("publishedAt", ""),
        }
        if debug_scores:
            item["debug"] = {
                "channelId": c.get("channelId"),
                "viewCount": c.get("viewCount"),
            }
        return item

    def _accept(c: dict[str, Any]) -> bool:
        vid = c.get("videoId")
        if not vid or vid in existing_ids:
            return False
        return bool(filter_duplicates(
            [{"title": c.get("title", ""), "artist": c.get("artist", "")}], songs
        ))

    confidence = _compute_confidence(ranked, max_results)
    low_confidence = confidence < _CONFIDENCE_THRESHOLD

    final: list[dict[str, Any]] = []
    if low_confidence:
        # Not confident enough: show only the freshest subscription uploads and
        # surface similar/new channels the user might like (no taste guessing).
        fresh = [c for c in ranked if c.get("source") in ("notification", "subscription_feed")]
        fresh.sort(key=lambda r: r.get("publishedAt", ""), reverse=True)
        new_channels = [c for c in diverse if _is_new_channel(c)]
        new_channels.sort(key=lambda r: -r.get("score", 0))

        seen_v: set[str] = set()
        for c in fresh + new_channels:
            if c["videoId"] in seen_v or not _accept(c):
                continue
            seen_v.add(c["videoId"])
            item = _to_item(c)
            if c in fresh:
                item["reason"] = item.get("reason") or "Latest from your subscriptions"
            else:
                item["reason"] = "New channel you may like"
            final.append(item)
            if len(final) >= max_results:
                break
        result_mode = "low_confidence_fresh"
    else:
        for c in diverse:
            if not _accept(c):
                continue
            final.append(_to_item(c))
            if len(final) >= max_results:
                break
        result_mode = mode

    return {
        "request_id": request_id,
        "profile": {**ALGO_PROFILE, "mode": result_mode, "requested_mode": mode},
        "confidence": confidence,
        "confidence_threshold": _CONFIDENCE_THRESHOLD,
        "low_confidence": low_confidence,
        "taste_profile": graph,
        "data": {
            "songs": final,
            "playlist": [],
            "nextPageToken": None,
        },
        "quota_used": quota_used(),
        "quota_max": max_calls(),
    }
