from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from app.db import tag_repository
from app.logic.tags.library_tagger import analyze_library
from app.logic.tags.tagging_service import tag_song
from app.logic.tags.universal_tags import get_vocabulary_by_dimension

router = APIRouter(prefix="/tags", tags=["tags"])


class AnalyzeTagsBody(BaseModel):
    video_ids: Optional[list[str]] = None
    analyze_all: bool = False
    limit: int = 50
    force: bool = False


@router.get("/vocabulary")
async def get_vocabulary():
    return get_vocabulary_by_dimension()


@router.get("/status")
async def get_tagging_status():
    """How much of the library is already tagged (auto-tagger progress)."""
    from app.logic.tags.auto_tagger import tagging_status

    return tagging_status()


@router.post("/auto/run")
async def run_auto_tag(batch_limit: int = 12):
    """Trigger one incremental tagging pass over not-yet-tagged songs."""
    from app.logic.tags.auto_tagger import run_auto_tag_pass

    return await run_auto_tag_pass(batch_limit=batch_limit)


@router.get("/song/{video_id}")
async def get_song_tags(video_id: str):
    try:
        tags = tag_repository.get_tags(video_id)
        return {"videoId": video_id, "tags": tags}
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail={"error": str(e)}) from e


@router.post("/analyze")
async def analyze_tags(body: AnalyzeTagsBody):
    try:
        if body.video_ids and len(body.video_ids) == 1 and not body.analyze_all:
            from app.logic.recommendations.playlist_service import load_playlist

            songs = load_playlist()
            song = next(
                (s for s in songs if (s.get("videoId") or s.get("id")) == body.video_ids[0]),
                {"videoId": body.video_ids[0]},
            )
            tags = await tag_song(song, force=body.force)
            return {"analyzed": 1, "skipped": 0, "tags": {body.video_ids[0]: tags}}

        result = await analyze_library(
            video_ids=body.video_ids,
            analyze_all=body.analyze_all,
            limit=body.limit,
            force=body.force,
        )
        return result
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail={"error": str(e)}) from e
