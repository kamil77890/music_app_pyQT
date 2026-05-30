"""Incremental background tagging.

Tags only songs that have no tags yet, in small batches, so the whole library
gets fully tagged over time without spending Gemini tokens on already-tagged
songs or huge one-shot requests.
"""

from __future__ import annotations

import logging
from typing import Any

from app.db import tag_repository
from app.logic.recommendations.playlist_service import load_playlist
from app.logic.tags.library_tagger import _enrich_with_id3
from app.logic.tags.tagging_service import tag_songs_batch

log = logging.getLogger(__name__)


def _song_id(song: dict[str, Any]) -> str:
    return song.get("videoId") or song.get("id") or ""


def tagging_status() -> dict[str, Any]:
    """How much of the library is already tagged."""
    songs = load_playlist()
    total = 0
    tagged = 0
    for s in songs:
        vid = _song_id(s)
        if not vid:
            continue
        total += 1
        if tag_repository.has_tags(vid):
            tagged += 1
    return {
        "total": total,
        "tagged": tagged,
        "untagged": total - tagged,
        "coverage": round(tagged / total, 3) if total else 0.0,
    }


def _untagged_songs(songs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for s in songs:
        vid = _song_id(s)
        if vid and not tag_repository.has_tags(vid):
            out.append(s)
    return out


async def run_auto_tag_pass(batch_limit: int = 12) -> dict[str, Any]:
    """Tag up to `batch_limit` not-yet-tagged songs. Cheap to call repeatedly:
    once everything is tagged it does nothing."""
    songs = load_playlist()
    if not songs:
        return {"tagged": 0, "remaining": 0, "total": 0}

    untagged = _untagged_songs(songs)
    if not untagged:
        return {"tagged": 0, "remaining": 0, "total": len(songs)}

    batch = [_enrich_with_id3(s) for s in untagged[:batch_limit]]
    results = await tag_songs_batch(batch)
    tagged_now = len(results)
    log.info(
        "Auto-tag pass: tagged %d, %d still untagged",
        tagged_now,
        len(untagged) - tagged_now,
    )
    return {
        "tagged": tagged_now,
        "remaining": max(0, len(untagged) - tagged_now),
        "total": len(songs),
    }
