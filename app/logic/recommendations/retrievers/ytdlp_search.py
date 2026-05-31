from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import yt_dlp

from app.db import subscription_repository
from app.logic.api_handler.handle_yt_discovery import (
    TOP_ARTIST_EXPLORE_SUFFIX_SOURCE,
    TOP_ARTIST_NEWEST_SOURCE,
    TOP_ARTIST_POPULAR_SOURCE,
    TOP_TITLE_NEWEST_SOURCE,
    TOP_TITLE_POPULAR_SOURCE,
    YT_EXPLORE_SOURCE,
)
from app.logic.recommendations.resolver import cover_url

log = logging.getLogger(__name__)

_YTDLP_OPTS = {
    "quiet": True,
    "skip_download": True,
    "extract_flat": True,
    "noplaylist": True,
}


def _published_at(entry: dict[str, Any]) -> str:
    timestamp = entry.get("timestamp")
    if timestamp:
        try:
            return datetime.fromtimestamp(int(timestamp), tz=timezone.utc).isoformat()
        except (TypeError, ValueError, OSError):
            pass

    upload_date = str(entry.get("upload_date") or "")
    if len(upload_date) == 8 and upload_date.isdigit():
        return f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}T00:00:00Z"

    return ""


def _entry_to_candidate(
    entry: dict[str, Any],
    *,
    source: str,
    query: str,
    reason: str,
) -> dict[str, Any] | None:
    vid = entry.get("id") or entry.get("url")
    if not vid:
        return None
    title = entry.get("title") or ""
    artist = entry.get("channel") or entry.get("uploader") or entry.get("uploader_id") or ""
    thumbs = entry.get("thumbnails") or []
    thumb = ""
    if thumbs:
        thumb = (thumbs[-1] or {}).get("url") or ""

    return {
        "videoId": str(vid),
        "title": title,
        "artist": artist,
        "channelId": entry.get("channel_id") or entry.get("uploader_id") or "",
        "publishedAt": _published_at(entry),
        "coverUrl": thumb or cover_url(str(vid)),
        "url": f"https://www.youtube.com/watch?v={vid}",
        "source": source,
        "reason": reason,
        "searchQuery": query,
        "viewCount": int(entry.get("view_count") or 0),
        "duration": entry.get("duration") or "",
        "tags": [],
    }


def search_ytdlp(
    query: str,
    *,
    max_results: int = 8,
    source: str = YT_EXPLORE_SOURCE,
    reason: str | None = None,
) -> list[dict[str, Any]]:
    query = (query or "").strip()
    if not query:
        return []
    try:
        with yt_dlp.YoutubeDL(_YTDLP_OPTS) as ydl:
            data = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
    except Exception:
        log.exception("yt-dlp recommendation search failed: %s", query)
        return []

    rows: list[dict[str, Any]] = []
    for entry in data.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        candidate = _entry_to_candidate(
            entry,
            source=source,
            query=query,
            reason=reason or f"yt-dlp search: {query}",
        )
        if candidate:
            rows.append(candidate)
    return rows


def _add_search(
    out: list[dict[str, Any]],
    seen: set[str],
    excluded: set[str],
    query: str,
    *,
    source: str,
    reason: str,
    max_results: int = 8,
    extra: dict[str, Any] | None = None,
) -> None:
    for row in search_ytdlp(query, max_results=max_results, source=source, reason=reason):
        vid = row.get("videoId")
        if not vid or vid in excluded or vid in seen:
            continue
        if extra:
            row.update(extra)
        seen.add(vid)
        out.append(row)


def _notification_candidates(excluded: set[str], seen: set[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for n in subscription_repository.list_notifications(unseen_only=True)[:15]:
        vid = n.get("videoId")
        if not vid or vid in excluded or vid in seen:
            continue
        seen.add(vid)
        out.append({
            "videoId": vid,
            "title": n.get("title", ""),
            "artist": n.get("channelTitle", ""),
            "channelId": n.get("channelId"),
            "publishedAt": n.get("publishedAt", ""),
            "coverUrl": n.get("cover") or cover_url(vid),
            "url": f"https://www.youtube.com/watch?v={vid}",
            "source": "notification",
            "reason": "Unseen subscription notification",
        })
    return out


def retrieve_ytdlp_candidates(
    graph: dict[str, Any],
    excluded: set[str],
    songs: list[dict[str, Any]],
    *,
    seed_video_id: str | None = None,
    mode: str = "focus",
    max_results: int = 120,
    interest_hint: str = "",
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    out.extend(_notification_candidates(excluded, seen))

    artists = [
        a for a in (graph.get("top_artists") or [])
        if (a.get("artist") or "").strip()
    ]
    library_artists = [a for a in artists if a.get("from_library")] or artists

    for rank, entry in enumerate(library_artists[:5]):
        artist = (entry.get("artist") or "").replace('"', "").strip()
        if not artist:
            continue
        hint = f" {interest_hint}" if interest_hint else ""
        _add_search(
            out, seen, excluded, f'"{artist}"{hint} music',
            source=TOP_ARTIST_POPULAR_SOURCE,
            reason=f"yt-dlp music search for library artist {artist}",
            max_results=8,
            extra={"library_artist_focus": artist, "library_artist_rank": rank, "focus_kind": "artist"},
        )
        _add_search(
            out, seen, excluded, f'"{artist}" official audio',
            source=TOP_ARTIST_NEWEST_SOURCE,
            reason=f"yt-dlp official audio search for library artist {artist}",
            max_results=6,
            extra={"library_artist_focus": artist, "library_artist_rank": rank, "focus_kind": "artist"},
        )
        if rank < 2 or mode in ("discover", "fresh"):
            _add_search(
                out, seen, excluded, f'"{artist}" lyrics',
                source=TOP_ARTIST_EXPLORE_SUFFIX_SOURCE,
                reason=f"yt-dlp lyrics search for library artist {artist}",
                max_results=5,
                extra={"library_artist_focus": artist, "library_artist_rank": rank, "focus_kind": "artist"},
            )
        if len(out) >= max_results:
            return out[:max_results]

    title_rows = graph.get("top_titles") or []
    for rank, entry in enumerate(title_rows[:8]):
        title = (entry.get("title") or "").replace('"', "").strip()
        artist = (entry.get("artist") or "").replace('"', "").strip()
        if not title:
            continue
        query = f'"{artist}" "{title}" music' if artist else f'"{title}" music'
        _add_search(
            out, seen, excluded, query,
            source=TOP_TITLE_POPULAR_SOURCE,
            reason=f"yt-dlp similar title search for {title}",
            max_results=6,
            extra={"library_title_focus": title, "library_title_rank": rank, "focus_kind": "title"},
        )
        if mode in ("discover", "fresh"):
            _add_search(
                out, seen, excluded, f'"{title}" cover remix music',
                source=TOP_TITLE_NEWEST_SOURCE,
                reason=f"yt-dlp discovery search around {title}",
                max_results=4,
                extra={"library_title_focus": title, "library_title_rank": rank, "focus_kind": "title"},
            )
        if len(out) >= max_results:
            return out[:max_results]

    if seed_video_id:
        seed = next(
            (s for s in songs if str(s.get("videoId") or s.get("id") or "") == seed_video_id),
            None,
        )
        if seed:
            title = (seed.get("title") or "").replace('"', "")
            artist = (seed.get("artist") or "").replace('"', "")
            _add_search(
                out, seen, excluded, f'"{artist}" "{title}" similar music',
                source="related",
                reason=f"yt-dlp search similar to {title[:40]}",
                max_results=12,
                extra={"seedVideoId": seed_video_id},
            )

    for item in (graph.get("music_oauth_items") or [])[:8]:
        title = (item.get("title") or "").replace('"', "").strip()
        channel = (item.get("channel_title") or "").replace('"', "").strip()
        vid = item.get("video_id")
        if vid and vid not in excluded and vid not in seen:
            seen.add(vid)
            out.append({
                "videoId": vid,
                "title": title,
                "artist": channel,
                "source": "oauth_music_liked",
                "reason": "From your YouTube likes/imports (music)",
                "coverUrl": cover_url(vid),
                "url": f"https://www.youtube.com/watch?v={vid}",
            })
        if title:
            query = f'"{channel}" "{title[:55]}" music' if channel else f'"{title[:55]}" music'
            _add_search(
                out, seen, excluded, query,
                source="oauth_similar",
                reason=f"yt-dlp search similar to liked/imported: {title[:35]}",
                max_results=5,
            )
        if len(out) >= max_results:
            return out[:max_results]

    for sub in subscription_repository.list_subscriptions()[:8]:
        channel = (sub.get("channelTitle") or "").replace('"', "").strip()
        if not channel:
            continue
        _add_search(
            out, seen, excluded, f'"{channel}" music latest',
            source="subscription_feed",
            reason=f"yt-dlp search from subscribed channel {channel}",
            max_results=5,
            extra={"channelId": sub.get("channelId")},
        )
        if len(out) >= max_results:
            return out[:max_results]

    tags = [str(t.get("tag") or "").replace("_", " ") for t in (graph.get("top_tags") or [])[:8]]
    primary_artist = (graph.get("primary_library_artist") or "").replace('"', "")
    for tag in tags:
        if not tag:
            continue
        query = f'"{primary_artist}" {tag} music' if primary_artist else f"{tag} music"
        _add_search(
            out, seen, excluded, query,
            source=YT_EXPLORE_SOURCE,
            reason=f"yt-dlp tag discovery search: {tag}",
            max_results=6,
        )
        if len(out) >= max_results:
            return out[:max_results]

    return out[:max_results]
