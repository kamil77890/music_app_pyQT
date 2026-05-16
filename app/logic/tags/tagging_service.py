from __future__ import annotations

import logging
import os
from typing import Any

from app.db import tag_repository
from app.logic.api_handler.handle_yt_service import create_youtube_service
from app.logic.tags.gemini_client import generate_json
from app.logic.tags.universal_tags import (
    filter_valid_tag_entries,
    format_vocabulary_for_prompt,
    normalize_raw_genre,
    validate_tag,
    year_to_era,
    get_dimension,
)
from app.utils.youtube_error_handler import youtube_api_error_handler

log = logging.getLogger(__name__)

BATCH_SIZE = int(os.environ.get("TAG_ANALYZE_BATCH_SIZE", "20"))

TAGGING_PROMPT = """You are a music tagging engine. Assign universal tags to each song.

ALLOWED TAGS ONLY (use exact snake_case ids):
{vocabulary}

RULES:
- Return 3-8 tags per song from the vocabulary only
- Include at least one genre tag when possible
- Add mood, energy, tempo, era, vocal, or context tags when inferable
- confidence: 0.0-1.0

OUTPUT JSON:
{{
  "songs": [
    {{
      "videoId": "...",
      "tags": [
        {{"tag": "nightcore", "dimension": "genre", "confidence": 0.9}}
      ]
    }}
  ]
}}

SONGS TO TAG:
{songs}
"""


@youtube_api_error_handler
def _fetch_youtube_metadata(video_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not video_ids:
        return {}
    youtube = create_youtube_service()
    resp = youtube.videos().list(
        part="snippet",
        id=",".join(video_ids[:50]),
    ).execute()
    result = {}
    for item in resp.get("items", []):
        vid = item.get("id")
        snippet = item.get("snippet", {})
        if vid:
            result[vid] = {
                "categoryId": snippet.get("categoryId"),
                "tags": snippet.get("tags", []),
                "description": (snippet.get("description") or "")[:200],
            }
    return result


def _id3_tags_for_song(song: dict[str, Any]) -> list[dict[str, Any]]:
    tags: list[dict[str, Any]] = []
    genre = song.get("genre") or song.get("id3_genre") or ""
    for g in normalize_raw_genre(genre):
        tags.append({"tag": g, "dimension": "genre", "confidence": 0.75, "source": "id3"})
    year = song.get("year") or song.get("id3_year")
    era = year_to_era(year)
    if era and validate_tag(era):
        tags.append({"tag": era, "dimension": "era", "confidence": 0.6, "source": "id3"})
    return tags


async def tag_song(song: dict[str, Any], *, force: bool = False) -> list[dict[str, Any]]:
    video_id = song.get("videoId") or song.get("id")
    if not video_id:
        return []
    if not force and tag_repository.has_tags(video_id):
        return tag_repository.get_tags(video_id)
    results = await tag_songs_batch([song], force=force)
    return results.get(video_id, [])


async def tag_songs_batch(
    songs: list[dict[str, Any]],
    *,
    force: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    to_analyze: list[dict[str, Any]] = []
    output: dict[str, list[dict[str, Any]]] = {}

    for song in songs:
        video_id = song.get("videoId") or song.get("id")
        if not video_id:
            continue
        if not force and tag_repository.has_tags(video_id):
            output[video_id] = tag_repository.get_tags(video_id)
        else:
            to_analyze.append(song)

    if not to_analyze:
        return output

    video_ids = [
        s.get("videoId") or s.get("id")
        for s in to_analyze
        if s.get("videoId") or s.get("id")
    ]
    yt_meta: dict[str, dict[str, Any]] = {}
    try:
        yt_meta = _fetch_youtube_metadata(video_ids)
    except Exception:
        log.exception("YouTube metadata fetch failed for tagging")

    enriched = []
    for song in to_analyze:
        vid = song.get("videoId") or song.get("id")
        entry = {
            "videoId": vid,
            "title": song.get("title", ""),
            "artist": song.get("artist", ""),
            "id3_genre": song.get("genre") or song.get("id3_genre"),
            "year": song.get("year") or song.get("id3_year"),
            "youtube": yt_meta.get(vid, {}),
        }
        enriched.append(entry)

    for i in range(0, len(enriched), BATCH_SIZE):
        batch = enriched[i : i + BATCH_SIZE]
        ai_results = await _gemini_tag_batch(batch)
        for item in batch:
            vid = item["videoId"]
            id3_tags = _id3_tags_for_song({
                "genre": item.get("id3_genre"),
                "year": item.get("year"),
            })
            ai_tags = ai_results.get(vid, [])
            merged = _merge_tags(id3_tags, ai_tags)
            tag_repository.set_tags(vid, merged)
            output[vid] = merged

    return output


async def _gemini_tag_batch(batch: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    import json

    prompt = TAGGING_PROMPT.format(
        vocabulary=format_vocabulary_for_prompt(),
        songs=json.dumps(batch, ensure_ascii=False),
    )
    data = await generate_json(prompt)
    if not data or not isinstance(data, dict):
        return {}

    result: dict[str, list[dict[str, Any]]] = {}
    for entry in data.get("songs", []):
        vid = entry.get("videoId")
        if not vid:
            continue
        raw_tags = entry.get("tags", [])
        valid = filter_valid_tag_entries([
            {
                "tag": t.get("tag"),
                "dimension": t.get("dimension") or get_dimension(t.get("tag", "")),
                "confidence": t.get("confidence", 0.7),
                "source": "ai",
            }
            for t in raw_tags
            if isinstance(t, dict)
        ])
        result[vid] = valid
    return result


def _merge_tags(*tag_lists: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_tag: dict[str, dict[str, Any]] = {}
    for tags in tag_lists:
        for t in tags:
            tag = t["tag"]
            if tag not in by_tag or t.get("confidence", 0) > by_tag[tag].get("confidence", 0):
                by_tag[tag] = t
    return list(by_tag.values())
