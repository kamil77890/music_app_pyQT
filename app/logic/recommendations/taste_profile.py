from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from typing import Any

from app.db import tag_repository
from app.logic.recommendations.playlist_service import get_playlist_path, load_playlist
from app.utils.music_utils import build_library_index, normalize


def library_hash() -> str:
    path = get_playlist_path()
    songs = load_playlist()
    if not path.is_file():
        return "empty"
    mtime = path.stat().st_mtime
    payload = f"{path}:{mtime}:{len(songs)}:taste_v2"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def build_taste_profile(*, use_cache: bool = True) -> dict[str, Any]:
    lib_hash = library_hash()
    if use_cache:
        cached = tag_repository.get_cached_taste_profile(lib_hash)
        if cached:
            return cached

    songs = load_playlist()
    _, existing_ids = build_library_index(songs)

    histogram = tag_repository.get_library_tag_histogram()
    by_dim = tag_repository.get_tag_counts_by_dimension()

    top_tags = [
        {"tag": tag, "weight": round(weight, 4)}
        for tag, weight in sorted(histogram.items(), key=lambda x: -x[1])[:15]
    ]

    artist_counts: Counter[str] = Counter()
    for s in songs:
        artist = (s.get("artist") or "").strip()
        if artist:
            artist_counts[artist] += 1
    total_artists = sum(artist_counts.values()) or 1
    top_artists = [
        {
            "artist": a,
            "weight": round(c / total_artists, 4),
            "song_count": c,
        }
        for a, c in artist_counts.most_common(10)
    ]

    primary_library_artist = top_artists[0]["artist"] if top_artists else None
    primary_library_artist_count = top_artists[0]["song_count"] if top_artists else 0

    norm_to_display: dict[str, str] = {}
    norm_to_artists: dict[str, Counter[str]] = defaultdict(Counter)
    title_by_norm: Counter[str] = Counter()

    for s in songs:
        raw_title = (s.get("title") or "").strip()
        if not raw_title or len(raw_title) < 2:
            continue
        nk = normalize(raw_title)
        if not nk:
            continue
        title_by_norm[nk] += 1
        if nk not in norm_to_display:
            norm_to_display[nk] = raw_title
        artist = (s.get("artist") or "").strip()
        if artist:
            norm_to_artists[nk][artist] += 1

    n_lib = len(songs) or 1
    top_titles: list[dict[str, Any]] = []
    for nk, c in title_by_norm.most_common(20):
        display = norm_to_display.get(nk, nk)
        maj_artist = norm_to_artists[nk].most_common(1)
        primary_for_title = maj_artist[0][0] if maj_artist else ""
        top_titles.append({
            "title": display,
            "artist": primary_for_title,
            "song_count": c,
            "weight": round(c / n_lib, 4),
        })

    era_weights = by_dim.get("era", {})
    top_eras = [
        {"era": era, "weight": round(w, 4)}
        for era, w in sorted(era_weights.items(), key=lambda x: -x[1])[:5]
    ]

    energy_weights = by_dim.get("energy", {})
    energy_avg = max(energy_weights, key=energy_weights.get) if energy_weights else "medium"

    profile = {
        "primary_library_artist": primary_library_artist,
        "primary_library_artist_count": primary_library_artist_count,
        "top_tags": top_tags,
        "top_artists": top_artists,
        "top_titles": top_titles,
        "top_eras": top_eras,
        "energy_avg": energy_avg,
        "tag_histogram": histogram,
        "by_dimension": by_dim,
        "library_size": len(songs),
        "excluded_video_ids": list(existing_ids),
        "library_hash": lib_hash,
    }

    tag_repository.save_taste_profile(lib_hash, profile)
    return profile
