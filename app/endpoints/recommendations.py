from fastapi import APIRouter, Query, HTTPException

from app.logic.recommendations.pipeline import run_pipeline
from app.logic.recommendations.playlist_service import load_playlist


router = APIRouter(tags=["Recommendations"])


@router.get("/recommendations")
async def get_recommendations(
    max_results: int = Query(10, ge=1, le=30),
):
    songs = load_playlist()

    if not songs:
        raise HTTPException(404, "playlist empty")

    profile, resolved = await run_pipeline(songs, max_results)

    return {
        "success": True,
        "profile": profile,
        "data": {
            "songs": resolved,
            "playlist": [],
            "nextPageToken": None,
        },
    }