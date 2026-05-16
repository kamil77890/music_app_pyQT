import json
import re
import logging

from google.api_core.exceptions import ResourceExhausted

from app.logic.tags.gemini_client import generate_json
from app.utils.music_utils import compact_json, extract_style_hint, song_key

log = logging.getLogger(__name__)


SYSTEM_PROMPT = """
You are a STRICT music recommendation engine.

GOAL:
Recommend NEW songs that match the user's taste.

CRITICAL RULES:
- NEVER recommend songs from the provided library
- NEVER repeat artist + title already present
- DO NOT suggest compilations, mixes, playlists
- DO NOT return "best of", "mix", "playlist" type videos
- Only return individual songs

MUST:
- match style, genre, energy, mood of the library
- stay close to listening patterns
- introduce NEW but similar artists/songs

OUTPUT FORMAT (STRICT JSON ONLY):
{
  "profile": {...},
  "recommendations": [
    {"title": "...", "artist": "..."}
  ]
}
"""


def fallback(songs, max_results, existing_keys):
    artists = list({s.get("artist") for s in songs if s.get("artist")})

    recs = []
    used = set(existing_keys)

    for a in artists:
        candidate = f"Deep cut {a} track"
        norm = song_key({"title": candidate, "artist": a})

        if norm in used:
            continue

        recs.append({
            "title": candidate,
            "artist": a
        })

        used.add(norm)

        if len(recs) >= max_results:
            break

    return {
        "profile": {"source": "fallback"},
        "recommendations": recs
    }


def build_exclusion_block(songs):
    seen = set()
    block = []

    for s in songs[:500]:
        title = (s.get("title") or "").strip()
        artist = (s.get("artist") or "").strip()

        if not title or not artist:
            continue

        key = f"{title.lower()}::{artist.lower()}"

        if key in seen:
            continue

        seen.add(key)
        block.append(f"{title} - {artist}")

    return block


async def ask_gemini(songs, existing_keys, max_results, tag_histogram: dict | None = None):
    style = extract_style_hint(songs)
    excluded = build_exclusion_block(songs)

    tag_block = ""
    if tag_histogram:
        top = sorted(tag_histogram.items(), key=lambda x: -x[1])[:12]
        tag_block = f"\nLIBRARY TAG PROFILE (top weights):\n{compact_json(dict(top))}\n"

    prompt = f"""
{SYSTEM_PROMPT}

STYLE HINT:
{compact_json(style)}
{tag_block}
CRITICAL EXCLUSION LIST:
You MUST NOT recommend ANY of these songs or variations of them:

{compact_json(excluded)}

RULE:
- no remasters
- no live versions
- no slowed / nightcore / sped up versions
- no reuploads of same track
- no playlist/mix videos

LIBRARY (sample):
{compact_json(songs[:80])}

Return ONLY NEW songs similar in style. Up to {max_results} recommendations.
"""

    try:
        data = await generate_json(prompt, temperature=0.25)
    except ResourceExhausted:
        log.warning("Gemini quota exceeded → fallback")
        return fallback(songs, max_results, existing_keys)

    if not data or not isinstance(data, dict):
        return fallback(songs, max_results, existing_keys)

    seen = set(existing_keys)
    filtered = []

    for r in data.get("recommendations", []):
        key = song_key(r)

        if key in seen:
            continue

        seen.add(key)
        filtered.append(r)

        if len(filtered) >= max_results:
            break

    data["recommendations"] = filtered
    return data
