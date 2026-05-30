from __future__ import annotations

import json
import logging
from typing import Any

from app.logic.tags.gemini_client import generate_json
from app.logic.tags.universal_tags import format_vocabulary_for_prompt
from app.utils.music_utils import compact_json, extract_style_hint

log = logging.getLogger(__name__)

ADVANCED_PROMPT = """You are an advanced music recommendation engine.

GOAL: Suggest NEW songs matching the user's taste profile. Use ONLY tags from the universal vocabulary.

UNIVERSAL TAGS:
{vocabulary}

TASTE PROFILE:
{profile}

STYLE HINT:
{style_hint}

EXCLUSION (do NOT recommend these artist-title pairs):
{exclusions}

RULES:
- Individual songs only (no playlists, mixes, compilations)
- Match top tags, mood, energy from profile
- Introduce similar but NEW artists
- Each recommendation must include predicted universal tags

OUTPUT JSON:
{{
  "profile": {{"summary": "..."}},
  "recommendations": [
    {{
      "title": "...",
      "artist": "...",
      "reason": "...",
      "tags": ["nightcore", "energetic", "2010s"],
      "confidence": 0.85
    }}
  ]
}}
"""


async def ask_gemini_advanced(
    taste_profile: dict[str, Any],
    songs: list[dict[str, Any]],
    max_results: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    style = extract_style_hint(songs)
    exclusions = []
    for s in songs[:80]:
        t = (s.get("title") or "").strip()
        a = (s.get("artist") or "").strip()
        if t and a:
            exclusions.append(f"{t} - {a}")

    compact_profile = {
        "top_tags": taste_profile.get("top_tags", [])[:8],
        "top_artists": taste_profile.get("top_artists", [])[:6],
        "top_titles": taste_profile.get("top_titles", [])[:8],
        "energy_avg": taste_profile.get("energy_avg"),
        "top_eras": taste_profile.get("top_eras", [])[:4],
    }

    prompt = ADVANCED_PROMPT.format(
        vocabulary=format_vocabulary_for_prompt(),
        profile=compact_json(compact_profile),
        style_hint=compact_json(style),
        exclusions=compact_json(exclusions[:80]),
    )

    data = await generate_json(prompt, temperature=0.3)
    if not data or not isinstance(data, dict):
        return {"source": "fallback"}, []

    profile = data.get("profile", {})
    recs = []
    for r in data.get("recommendations", []):
        if not isinstance(r, dict):
            continue
        recs.append({
            "title": r.get("title", ""),
            "artist": r.get("artist", ""),
            "reason": r.get("reason", ""),
            "tags": r.get("tags", []),
            "geminiConfidence": r.get("confidence", 0.8),
            "source": "gemini",
        })
        if len(recs) >= max_results * 2:
            break
    return profile, recs
