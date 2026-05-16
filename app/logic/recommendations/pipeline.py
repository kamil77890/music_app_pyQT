"""YouTube + library-based recommendations only (no LLM)."""

from app.logic.recommendations.advanced_pipeline import run_youtube_recommendations


async def run_pipeline(songs, max_results):
    return await run_youtube_recommendations(songs, max_results)
