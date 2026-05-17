from __future__ import annotations

import logging
from typing import Any, Literal

from app.logic.recommendations.recommendation_orchestrator import (
    run_recommendation_orchestrator,
)

log = logging.getLogger(__name__)

Mode = Literal["focus", "discover", "fresh"]


async def run_advanced_pipeline(
    max_results: int = 10,
    seed_video_id: str | None = None,
    refresh_tags: bool = False,
    *,
    mode: Mode = "focus",
    use_llm_rerank: bool = False,
    max_per_channel: int = 2,
    debug_scores: bool = False,
) -> dict[str, Any]:
    _ = refresh_tags
    return await run_recommendation_orchestrator(
        max_results=max_results,
        seed_video_id=seed_video_id,
        mode=mode,
        use_llm_rerank=use_llm_rerank,
        max_per_channel=max_per_channel,
        debug_scores=debug_scores,
    )


async def run_youtube_recommendations(songs: list[dict[str, Any]], max_results: int):
    _ = songs
    result = await run_advanced_pipeline(max_results=max_results)
    return result["profile"], result["data"]["songs"]
