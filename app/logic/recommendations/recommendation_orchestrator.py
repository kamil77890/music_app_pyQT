from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Literal

from app.logic.recommendations.candidate_enrichment import enrich_candidates
from app.logic.recommendations.music_filter import filter_music_candidates
from app.logic.recommendations.deduper import filter_duplicates
from app.logic.recommendations.diversity_mixer import apply_diversity
from app.logic.recommendations.playlist_service import load_playlist
from app.logic.recommendations.quota_tracker import max_calls, reset, used as quota_used
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
from app.exceptions.youtube_errors import YouTubeQuotaExceededError
from app.logic.recommendations.user_taste_graph import build_user_taste_graph

log = logging.getLogger(__name__)


Mode = Literal["focus", "discover", "fresh"]

ALGO_PROFILE = {
    "source": "youtube_multi_retriever",
    "description": "Multi-source YouTube recommendations with behavioral taste graph",
}


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
        g["top_eras"] = [{"era": "2020s", "weight": 1.0}] + [
            e for e in eras if e.get("era") != "2020s"
        ][:4]
    return g


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

    def sync_retrievers() -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []

        def _run(name: str, fn) -> bool:
            try:
                out.extend(fn())
                return True
            except YouTubeQuotaExceededError:
                log.warning("YouTube quota hit at %s — using partial candidates", name)
                return False
            except Exception:
                log.exception("Retriever %s failed", name)
                return True

        if not _run("oauth_music", lambda: retrieve_oauth_music(graph, excluded)):
            pass
        if not _run(
            "library_artists",
            lambda: retrieve_library_artists(
                graph_for_discovery, excluded, interest_hint=hint
            ),
        ):
            return out
        if not _run(
            "library_titles",
            lambda: retrieve_library_titles(graph, excluded, interest_hint=hint),
        ):
            return out
        _run("tag_queries", lambda: retrieve_tag_queries(graph, excluded))
        _run(
            "related",
            lambda: retrieve_related(graph, excluded, seed_video_id=seed_video_id),
        )
        _run(
            "subscriptions",
            lambda: retrieve_subscription_candidates(graph, excluded),
        )
        _run("notifications", lambda: retrieve_notification_candidates(excluded))
        if quota_used() < max_calls() - 2:
            explore_n = 14 if mode == "discover" else 8
            _run(
                "explore",
                lambda: retrieve_explore(graph, excluded, num_queries=explore_n),
            )
            _run(
                "albums",
                lambda: retrieve_album_candidates(graph_for_discovery, excluded),
            )
        return out

    sync_batch = await asyncio.to_thread(sync_retrievers)
    candidates.extend(sync_batch)

    gemini_batch = await retrieve_gemini_queries(graph, excluded)
    candidates.extend(gemini_batch)

    candidates = await enrich_candidates(candidates)
    candidates = filter_music_candidates(candidates, min_score=0.4)

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

    final: list[dict[str, Any]] = []
    for c in diverse:
        if c.get("videoId") and c["videoId"] in existing_ids:
            continue
        if not c.get("videoId"):
            continue
        title = c.get("title", "")
        artist = c.get("artist", "")
        if not filter_duplicates([{"title": title, "artist": artist}], songs):
            continue
        item: dict[str, Any] = {
            "videoId": c["videoId"],
            "title": title,
            "artist": artist,
            "coverUrl": c.get("coverUrl") or cover_url(c["videoId"]),
            "url": f"https://www.youtube.com/watch?v={c['videoId']}",
            "score": c.get("score", 0),
            "matchedTags": c.get("matchedTags") or c.get("tags", []),
            "source": c.get("source", "unknown"),
            "reason": c.get("reason", ""),
        }
        if debug_scores:
            item["debug"] = {
                "channelId": c.get("channelId"),
                "viewCount": c.get("viewCount"),
            }
        final.append(item)
        if len(final) >= max_results:
            break

    return {
        "request_id": request_id,
        "profile": {**ALGO_PROFILE, "mode": mode},
        "taste_profile": graph,
        "data": {
            "songs": final,
            "playlist": [],
            "nextPageToken": None,
        },
        "quota_used": quota_used(),
        "quota_max": max_calls(),
    }
