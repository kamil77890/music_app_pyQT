from __future__ import annotations

import re
from typing import Any

TAG_VOCABULARY: dict[str, list[str]] = {
    "genre": [
        "rock", "pop", "electronic", "hip_hop", "jazz", "classical", "metal",
        "indie", "r_and_b", "country", "latin", "k_pop", "nightcore", "folk",
        "blues", "reggae", "punk", "soul", "funk", "ambient", "house", "techno",
        "dubstep", "trap", "alternative",
    ],
    "mood": [
        "energetic", "chill", "melancholic", "uplifting", "dark", "romantic",
        "aggressive", "nostalgic", "dreamy", "epic",
    ],
    "energy": ["low", "medium", "high"],
    "tempo": ["slow", "mid", "fast"],
    "era": ["pre_80s", "80s", "90s", "2000s", "2010s", "2020s"],
    "vocal": ["instrumental", "vocal_heavy"],
    "context": ["workout", "focus", "party", "sleep", "driving"],
}

_ALL_TAGS: frozenset[str] = frozenset(
    tag for tags in TAG_VOCABULARY.values() for tag in tags
)

_TAG_TO_DIMENSION: dict[str, str] = {
    tag: dim for dim, tags in TAG_VOCABULARY.items() for tag in tags
}

_SKIP_GENRES = frozenset({"unknown", "", "unknown genre"})

_GENRE_ALIASES: dict[str, str] = {
    "r&b": "r_and_b",
    "rnb": "r_and_b",
    "rhythm and blues": "r_and_b",
    "hip hop": "hip_hop",
    "hip-hop": "hip_hop",
    "edm": "electronic",
    "dance": "electronic",
    "kpop": "k_pop",
    "k-pop": "k_pop",
    "r&b/soul": "r_and_b",
    "drum and bass": "electronic",
    "dnb": "electronic",
    "synthwave": "electronic",
    "lo-fi": "chill",
    "lofi": "chill",
    "night core": "nightcore",
}


def validate_tag(tag: str) -> bool:
    return tag in _ALL_TAGS


def get_dimension(tag: str) -> str | None:
    return _TAG_TO_DIMENSION.get(tag)


def normalize_raw_genre(genre_string: str) -> list[str]:
    if not genre_string or genre_string.lower().strip() in _SKIP_GENRES:
        return []
    candidates: list[str] = []
    for part in re.split(r"[,;/&]", genre_string):
        g = part.strip().lower().replace(" ", "_").replace("-", "_")
        if not g or g in _SKIP_GENRES:
            continue
        if g in _GENRE_ALIASES:
            g = _GENRE_ALIASES[g]
        if validate_tag(g):
            candidates.append(g)
        elif g.replace("_", "") in _GENRE_ALIASES:
            mapped = _GENRE_ALIASES[g.replace("_", " ")]
            if validate_tag(mapped):
                candidates.append(mapped)
    return list(dict.fromkeys(candidates))


def year_to_era(year: int | str | None) -> str | None:
    if year is None:
        return None
    try:
        y = int(str(year)[:4])
    except (ValueError, TypeError):
        return None
    if y < 1980:
        return "pre_80s"
    if y < 1990:
        return "80s"
    if y < 2000:
        return "90s"
    if y < 2010:
        return "2000s"
    if y < 2020:
        return "2010s"
    return "2020s"


def format_vocabulary_for_prompt() -> str:
    lines = []
    for dim, tags in TAG_VOCABULARY.items():
        lines.append(f"{dim}: {', '.join(tags)}")
    return "\n".join(lines)


def get_vocabulary_by_dimension() -> dict[str, list[str]]:
    return {dim: list(tags) for dim, tags in TAG_VOCABULARY.items()}


def filter_valid_tag_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    valid = []
    for entry in entries:
        tag = (entry.get("tag") or "").strip()
        if not validate_tag(tag):
            continue
        dim = entry.get("dimension") or get_dimension(tag)
        conf = float(entry.get("confidence", 0.7))
        conf = max(0.0, min(1.0, conf))
        valid.append({
            "tag": tag,
            "dimension": dim,
            "confidence": conf,
            "source": entry.get("source", "ai"),
        })
    return valid
