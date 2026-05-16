from __future__ import annotations

import logging
import os
from typing import Any

from app.logic.recommendations.playlist_service import load_playlist
from app.logic.tags.tagging_service import tag_songs_batch

log = logging.getLogger(__name__)


def _enrich_with_id3(song: dict[str, Any]) -> dict[str, Any]:
    path = song.get("path") or song.get("file_path")
    if not path or not os.path.isfile(path):
        return song
    try:
        from app.logic.metadata.audio_tags import read_genre_year

        meta = read_genre_year(path)
        enriched = dict(song)
        if meta.get("genre"):
            enriched["genre"] = meta["genre"]
        if meta.get("year"):
            enriched["year"] = meta["year"]
        return enriched
    except Exception:
        log.debug("ID3 read failed for %s", path)
        return song


async def analyze_library(
    *,
    video_ids: list[str] | None = None,
    analyze_all: bool = False,
    limit: int = 50,
    force: bool = False,
) -> dict[str, Any]:
    songs = load_playlist()
    if not songs:
        return {"analyzed": 0, "skipped": 0, "tags": {}}

    if video_ids:
        id_set = set(video_ids)
        targets = [s for s in songs if (s.get("videoId") or s.get("id")) in id_set]
    elif analyze_all:
        targets = songs
    else:
        targets = songs[:limit]

    targets = [_enrich_with_id3(s) for s in targets[:limit]]
    if not targets:
        return {"analyzed": 0, "skipped": 0, "tags": {}}

    results = await tag_songs_batch(targets, force=force)
    return {
        "analyzed": len(results),
        "skipped": len(targets) - len(results),
        "tags": {vid: tags for vid, tags in results.items()},
    }
