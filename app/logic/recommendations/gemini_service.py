import json
import re
import os
import logging

import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted

from app.utils.music_utils import compact_json, extract_style_hint

log = logging.getLogger(__name__)


_MODEL = None


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


def fallback(songs, max_results, existing_titles):
    artists = list({s.get("artist") for s in songs if s.get("artist")})

    recs = []
    used = set(existing_titles)

    for a in artists:
        candidate = f"Deep cut {a} track"
        norm = candidate.lower()

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
    """
    Builds a strict exclusion list for Gemini to avoid duplicates.
    Includes title + artist normalization-safe format.
    """
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


def _get_model():
    global _MODEL

    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Missing GEMINI_API_KEY")

    genai.configure(api_key=key)

    _MODEL = genai.GenerativeModel(
        model_name="gemini-2.5-flash-lite",
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json",
            temperature=0.25,
        ),
    )

    return _MODEL



async def ask_gemini(songs, existing_titles, max_results):
    model = _get_model()

    style = extract_style_hint(songs)

    excluded = build_exclusion_block(songs)

    prompt = f"""
{SYSTEM_PROMPT}

CRITICAL EXCLUSION LIST:
You MUST NOT recommend ANY of these songs or variations of them:

{compact_json(excluded)}

RULE:
- no remasters
- no live versions
- no slowed / nightcore / sped up versions
- no reuploads of same track
- no playlist/mix videos

LIBRARY:
{compact_json(songs)}

Return ONLY NEW songs similar in style.
"""

    try:
        res = await model.generate_content_async(prompt)
        raw = (res.text or "").strip()

    except ResourceExhausted:
        log.warning("Gemini quota exceeded → fallback")
        return fallback(songs, max_results, existing_titles)

    except Exception as e:
        log.warning(f"Gemini error: {e}")
        return fallback(songs, max_results, existing_titles)

    raw = re.sub(r"^```[^\n]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)

    try:
        data = json.loads(raw)
    except Exception:
        return fallback(songs, max_results, existing_titles)

    # 🔥 HARD FILTER DUPLICATES HERE (IMPORTANT FIX)
    seen = set(existing_titles)
    filtered = []

    for r in data.get("recommendations", []):
        key = f"{r.get('title','').lower()}_{r.get('artist','').lower()}"

        if key in seen:
            continue

        seen.add(key)
        filtered.append(r)

        if len(filtered) >= max_results:
            break

    data["recommendations"] = filtered
    return data