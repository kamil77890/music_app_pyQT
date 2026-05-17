from __future__ import annotations

import random
from typing import Any

from app.logic.api_handler.handle_yt_discovery import (
    build_expanded_discovery_queries,
    build_tag_search_queries,
    run_exploratory_youtube_searches,
    search_by_query,
)
from app.logic.recommendations.quota_tracker import can_call, record


def _tag_search_pass(queries: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    orders = ("relevance", "viewCount", "date", "rating")
    for q in queries:
        if not can_call(1):
            break
        order = random.choice(orders)
        rows, tok = search_by_query(q, 10, order=order)
        record(1)
        out.extend(rows)
        if tok and random.random() < 0.38 and can_call(1):
            rows2, _ = search_by_query(q, 8, order=order, page_token=tok)
            record(1)
            out.extend(rows2)
    return out


def retrieve_tag_queries(
    graph: dict[str, Any],
    excluded: set[str],
) -> list[dict[str, Any]]:
    queries = build_tag_search_queries(graph, count=8)
    if not queries or not can_call(2):
        return []
    rows = _tag_search_pass(queries)
    return [r for r in rows if r.get("videoId") not in excluded]


def retrieve_explore(
    graph: dict[str, Any],
    excluded: set[str],
    *,
    num_queries: int | None = None,
) -> list[dict[str, Any]]:
    budget = graph.get("exploration_budget", 0.2)
    nq = num_queries or max(8, int(16 * budget))
    if not can_call(3):
        return []
    pool = build_expanded_discovery_queries(graph, max_queries=80)
    rows = run_exploratory_youtube_searches(
        pool,
        excluded,
        num_queries=nq,
        take_per_query=5,
    )
    record(3)
    return rows
