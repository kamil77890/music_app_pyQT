from __future__ import annotations

from typing import Any

from app.logic.api_handler.handle_yt_albums import run_deep_search, run_fetch_album_tracks
from app.logic.api_handler.handle_yt_discovery import (
    discover_from_library_top_artists,
    discover_from_library_titles,
)
from app.logic.recommendations.quota_tracker import can_call, record


def retrieve_library_artists(
    graph: dict[str, Any],
    excluded: set[str],
    *,
    interest_hint: str = "",
) -> list[dict[str, Any]]:
    if not can_call(4):
        return []
    artists = [
        a for a in graph.get("top_artists", [])
        if a.get("from_library") or a.get("song_count", 0) > 0
    ] or graph.get("top_artists", [])

    rows = discover_from_library_top_artists(
        artists,
        excluded,
        interest_hint=interest_hint,
        primary_popular=5,
        primary_newest=4,
        extra_artists=3,
        extra_popular=3,
        extra_newest=2,
    )
    record(4)
    return rows


def retrieve_library_titles(
    graph: dict[str, Any],
    excluded: set[str],
    *,
    interest_hint: str = "",
) -> list[dict[str, Any]]:
    if not can_call(3):
        return []
    rows = discover_from_library_titles(
        graph.get("top_titles", []),
        excluded,
        interest_hint=interest_hint,
        depth=8,
        popular_per=3,
        newest_per=2,
    )
    record(3)
    return rows


def retrieve_album_candidates(
    graph: dict[str, Any],
    excluded: set[str],
) -> list[dict[str, Any]]:
    if not can_call(2):
        return []
    artist = graph.get("primary_library_artist")
    if not artist:
        return []
    try:
        result = run_deep_search(f'"{artist}" official album')
    except Exception:
        return []
    record(2)
    out: list[dict[str, Any]] = []
    albums = (result.get("albums") or [])[:2]
    for alb in albums:
        pid = alb.get("playlist_id") or alb.get("id")
        if not pid:
            continue
        try:
            tracks = run_fetch_album_tracks(pid, alb.get("title", ""))
        except Exception:
            continue
        for track in tracks[:3]:
            vid = track.get("videoId") or (track.get("id") or {}).get("videoId")
            if not vid or vid in excluded:
                continue
            out.append({
                "videoId": vid,
                "title": track.get("title", ""),
                "artist": track.get("artist", artist),
                "source": "album_retriever",
                "reason": f"Album track from {artist}",
            })
    return out
