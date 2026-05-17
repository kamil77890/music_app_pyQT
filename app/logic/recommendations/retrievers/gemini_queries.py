from __future__ import annotations

import json
import logging
from typing import Any

from app.logic.api_handler.handle_yt_discovery import search_by_query
from app.logic.recommendations.quota_tracker import can_call, record
from app.logic.tags.gemini_client import generate_json
from app.utils.music_utils import compact_json

log = logging.getLogger(__name__)

QUERY_PROMPT = """Given this music taste profile, output 6 YouTube search queries (short strings) to discover NEW songs.
Profile: {profile}
Output JSON: {{"queries": ["query1", "query2", ...]}}"""


async def retrieve_gemini_queries(
    graph: dict[str, Any],
    excluded: set[str],
) -> list[dict[str, Any]]:
    if not can_call(3):
        return []
    compact = {
        "top_tags": graph.get("top_tags", [])[:8],
        "top_artists": graph.get("top_artists", [])[:5],
        "energy_avg": graph.get("energy_avg"),
    }
    try:
        data = await generate_json(
            QUERY_PROMPT.format(profile=compact_json(compact)),
            temperature=0.4,
        )
    except Exception:
        log.exception("Gemini query generation failed")
        return []

    queries: list[str] = []
    if isinstance(data, dict):
        raw = data.get("queries") or []
        queries = [str(q).strip() for q in raw if q][:6]

    out: list[dict[str, Any]] = []
    for q in queries:
        if not q or not can_call(1):
            break
        rows, _ = search_by_query(f"{q} music", 8, order="relevance")
        record(1)
        for c in rows:
            vid = c.get("videoId")
            if vid and vid not in excluded:
                c["source"] = "gemini_query"
                c["reason"] = f"Gemini suggested search: {q}"
                out.append(c)
    return out
