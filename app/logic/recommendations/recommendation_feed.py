"""Background recommendation feed.

Periodically runs the recommendation orchestrator to discover NEW items and
accumulates them in a rolling feed stored on disk. Clients read the feed
instantly (no live YouTube/LLM cost on the request path).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from app.storage import json_store

log = logging.getLogger(__name__)

# Dict-shaped store (json_store defaults *_dict.json files to {}).
FEED_FILE = "recommendation_feed_dict.json"
MAX_FEED_ITEMS = int(os.environ.get("RECOMMENDATION_FEED_MAX_ITEMS", "200"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_feed(limit: int | None = None) -> dict[str, Any]:
    data = json_store.read(FEED_FILE)
    if not isinstance(data, dict):
        data = {}
    items = data.get("items", [])
    if limit:
        items = items[:limit]
    return {
        "updatedAt": data.get("updatedAt"),
        "lastConfidence": data.get("lastConfidence"),
        "count": len(data.get("items", [])),
        "items": items,
    }


async def refresh_feed(max_results: int = 25, mode: str = "discover") -> dict[str, Any]:
    """Run one discovery pass and merge newly found items into the feed."""
    from app.logic.recommendations.recommendation_orchestrator import (
        run_recommendation_orchestrator,
    )

    result = await run_recommendation_orchestrator(max_results=max_results, mode=mode)
    new_items = result.get("data", {}).get("songs", [])

    with json_store.locked():
        data = json_store.read_unlocked(FEED_FILE)
        if not isinstance(data, dict):
            data = {}
        existing_items = data.get("items", [])
        existing_ids = {i.get("videoId") for i in existing_items}

        added: list[dict[str, Any]] = []
        now = _now_iso()
        for item in new_items:
            vid = item.get("videoId")
            if not vid or vid in existing_ids:
                continue
            existing_ids.add(vid)
            entry = dict(item)
            entry["discoveredAt"] = now
            added.append(entry)

        # Newest discoveries first, capped.
        merged = added + existing_items
        merged = merged[:MAX_FEED_ITEMS]

        json_store.write_unlocked(
            FEED_FILE,
            {
                "updatedAt": now,
                "lastConfidence": result.get("confidence"),
                "items": merged,
            },
        )

    log.info("Recommendation feed refreshed: +%d new (total %d)", len(added), len(merged))
    return {
        "added": len(added),
        "total": len(merged),
        "confidence": result.get("confidence"),
        "updatedAt": now,
    }
