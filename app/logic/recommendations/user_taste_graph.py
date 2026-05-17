from __future__ import annotations

import hashlib
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from app.db import (
    event_repository,
    feedback_repository,
    oauth_repository,
    subscription_repository,
    tag_repository,
)
from app.db import tag_repository as tag_repo
from app.logic.recommendations.music_filter import is_likely_music, music_likelihood
from app.logic.recommendations.playlist_service import get_playlist_path, load_playlist
from app.utils.music_utils import build_library_index, normalize


def graph_hash() -> str:
    path = get_playlist_path()
    songs = load_playlist()
    if not path.is_file():
        base = "empty"
    else:
        base = f"{path}:{path.stat().st_mtime}:{len(songs)}"
    ev = event_repository.events_hash_suffix()
    oauth = "yt1" if oauth_repository.is_connected() else "yt0"
    payload = f"{base}:{ev}:{oauth}:taste_graph_v2"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _legacy_liked_video_ids() -> set[str]:
    db_path = Path("database.db")
    if not db_path.is_file():
        return set()
    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute("SELECT videoId FROM songs WHERE liked = 1 AND videoId IS NOT NULL")
        rows = cur.fetchall()
        conn.close()
        return {str(r[0]) for r in rows if r[0]}
    except sqlite3.Error:
        return set()


def _classify_oauth_items() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    music: list[dict[str, Any]] = []
    other: list[dict[str, Any]] = []
    for item in oauth_repository.list_imported_by_source(limit=500):
        title = item.get("title") or ""
        ch = item.get("channel_title") or ""
        if is_likely_music(title, channel_title=ch, min_score=0.38):
            item = dict(item)
            item["music_likelihood"] = music_likelihood(title, channel_title=ch)
            music.append(item)
        else:
            other.append(item)
    music.sort(key=lambda x: -x.get("music_likelihood", 0))
    return music, other


def _merge_artist_weights(
    library: Counter[str],
    behavioral: Counter[str],
    imported_music: Counter[str],
) -> list[dict[str, Any]]:
    all_artists = set(library) | set(behavioral) | set(imported_music)
    lib_total = sum(library.values()) or 1
    beh_total = sum(behavioral.values()) or 1
    imp_total = sum(imported_music.values()) or 1

    merged: list[tuple[float, int, str, dict[str, Any]]] = []
    for artist in all_artists:
        lib_count = library.get(artist, 0)
        lib_w = (lib_count / lib_total) * 2.0
        beh_w = (behavioral.get(artist, 0) / beh_total) * 1.5
        imp_w = (imported_music.get(artist, 0) / imp_total) * 0.35
        weight = lib_w + beh_w + imp_w
        merged.append((
            weight,
            lib_count,
            artist,
            {
                "artist": artist,
                "weight": round(weight, 4),
                "song_count": lib_count,
                "play_count": behavioral.get(artist, 0),
                "import_music_count": imported_music.get(artist, 0),
                "from_library": lib_count > 0,
            },
        ))

    merged.sort(key=lambda x: (-x[1], -x[0]))
    return [entry for _, _, _, entry in merged[:15]]


def build_user_taste_graph(*, use_cache: bool = True) -> dict[str, Any]:
    g_hash = graph_hash()
    if use_cache:
        cached = tag_repo.get_cached_taste_profile(g_hash)
        if cached and cached.get("graph_version") == 2:
            return cached

    songs = load_playlist()
    _, existing_ids = build_library_index(songs)

    histogram = tag_repository.get_library_tag_histogram()
    by_dim = tag_repository.get_tag_counts_by_dimension()
    behavioral = event_repository.get_behavioral_aggregates()
    negative = feedback_repository.get_negative_signals()
    liked_ids = feedback_repository.get_liked_video_ids() | _legacy_liked_video_ids()

    music_oauth, _other_oauth = _classify_oauth_items()

    top_tags = [
        {"tag": tag, "weight": round(weight, 4)}
        for tag, weight in sorted(histogram.items(), key=lambda x: -x[1])[:15]
    ]

    library_artists: Counter[str] = Counter()
    for s in songs:
        artist = (s.get("artist") or "").strip()
        if artist and artist.lower() not in ("unknown artist", "unknown"):
            library_artists[artist] += 1

    behavioral_artists: Counter[str] = Counter()
    for entry in behavioral.get("top_artists", []):
        a = (entry.get("artist") or "").strip()
        if a:
            behavioral_artists[a] += entry.get("play_count", 1)

    imported_music_artists: Counter[str] = Counter()
    for item in music_oauth:
        ch = (item.get("channel_title") or "").strip()
        if ch:
            imported_music_artists[ch] += 1

    top_artists = _merge_artist_weights(
        library_artists, behavioral_artists, imported_music_artists
    )

    library_primary = next(
        (a for a in top_artists if a.get("song_count", 0) > 0),
        top_artists[0] if top_artists else None,
    )

    channel_weights: dict[str, float] = {}
    for sub in subscription_repository.list_subscriptions():
        cid = sub.get("channelId")
        if cid:
            channel_weights[cid] = channel_weights.get(cid, 0.5) + 0.3
    for entry in behavioral.get("top_channels", []):
        cid = entry.get("channel_id")
        if cid:
            channel_weights[cid] = channel_weights.get(cid, 0) + entry.get("play_count", 1) * 0.1

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
        maj = norm_to_artists[nk].most_common(1)
        primary = maj[0][0] if maj else ""
        top_titles.append({
            "title": display,
            "artist": primary,
            "song_count": c,
            "weight": round(c / n_lib, 4),
        })

    era_weights = by_dim.get("era", {})
    top_eras = [
        {"era": era, "weight": round(w, 4)}
        for era, w in sorted(era_weights.items(), key=lambda x: -x[1])[:5]
    ]
    energy_weights = by_dim.get("energy", {})
    energy_avg = (
        max(energy_weights, key=energy_weights.get) if energy_weights else "medium"
    )

    skip_rate = behavioral.get("skip_rate", 0.0)
    exploration_budget = min(0.45, 0.15 + skip_rate * 0.5)

    seed_video_ids: list[str] = []
    for s in songs:
        vid = s.get("videoId") or s.get("id")
        if vid:
            seed_video_ids.append(str(vid))
    for item in music_oauth[:15]:
        vid = item.get("video_id")
        if vid and vid not in seed_video_ids:
            seed_video_ids.append(vid)
    beh_seeds = event_repository.get_top_seed_video_ids(limit=5)
    for vid in beh_seeds:
        if vid not in seed_video_ids:
            seed_video_ids.append(vid)

    graph = {
        "graph_version": 2,
        "primary_library_artist": library_primary["artist"] if library_primary else None,
        "primary_library_artist_count": library_primary.get("song_count", 0) if library_primary else 0,
        "top_tags": top_tags,
        "top_artists": top_artists,
        "top_titles": top_titles,
        "top_eras": top_eras,
        "energy_avg": energy_avg,
        "tag_histogram": histogram,
        "by_dimension": by_dim,
        "library_size": len(songs),
        "excluded_video_ids": list(existing_ids),
        "library_hash": g_hash,
        "behavioral": behavioral,
        "negative": negative,
        "liked_video_ids": list(liked_ids),
        "channel_weights": channel_weights,
        "exploration_budget": round(exploration_budget, 3),
        "seed_video_ids": seed_video_ids[:12],
        "oauth_connected": oauth_repository.is_connected(),
        "imported_yt_count": len(music_oauth) + len(_other_oauth),
        "imported_music_count": len(music_oauth),
        "music_oauth_items": [
            {
                "video_id": i.get("video_id"),
                "title": i.get("title"),
                "channel_title": i.get("channel_title"),
                "source": i.get("source"),
            }
            for i in music_oauth[:20]
        ],
    }

    tag_repo.save_taste_profile(g_hash, graph)
    return graph


def build_taste_profile_compat(*, use_cache: bool = True) -> dict[str, Any]:
    return build_user_taste_graph(use_cache=use_cache)
