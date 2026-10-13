import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from app.exceptions.youtube_errors import (
    YouTubeQuotaExceededError,
    YouTubeAccessDeniedError,
    YouTubeAPIError,
)
from app.logic.api_handler.handle_yt import get_song_by_string
from app.logic.api_handler.handle_playlist_search import (
    get_playlist_search,
    get_playlist_songs_paginated,
)
from app.logic.recommendations.retrievers.ytdlp_search import search_ytdlp
from app.models.song import Song

router = APIRouter()
log = logging.getLogger(__name__)

# Hard cap for the (remote) YouTube Data API. If it is slow or the TCP
# connection stalls, we fall back to a local yt-dlp search instead of leaving
# the phone waiting until it times out.
_SEARCH_TIMEOUT_SECONDS = float(os.environ.get("SEARCH_TIMEOUT_SECONDS", "12"))
_FALLBACK_LIMIT = int(os.environ.get("SEARCH_FALLBACK_LIMIT", "10"))

# "ytdlp" (default) searches locally — fast and independent of Google's API.
# Set SEARCH_BACKEND=youtube_api to try the YouTube Data API first, with the
# local yt-dlp search as a fallback when it is slow or unavailable.
_SEARCH_BACKEND = os.environ.get("SEARCH_BACKEND", "ytdlp").strip().lower()


def _format_views(raw_views: int) -> str:
    if raw_views >= 1_000_000:
        return f"{raw_views / 1_000_000:.1f}M"
    if raw_views >= 1_000:
        return f"{raw_views / 1_000:.1f}K"
    return str(raw_views)


def _ytdlp_fallback_results(q: str, limit: int = _FALLBACK_LIMIT) -> Dict[str, Any]:
    """Local yt-dlp search, shaped like the YouTube Data API response."""
    rows = search_ytdlp(q, max_results=limit, reason=f"search fallback: {q}")
    songs: List[Any] = []
    for idx, row in enumerate(rows):
        try:
            duration = int(row.get("duration")) if row.get("duration") else 0
        except (TypeError, ValueError):
            duration = 0
        songs.append(
            Song(
                id=str(row.get("videoId") or idx),
                title=row.get("title") or "Unknown Title",
                artist=row.get("artist") or "Unknown Artist",
                duration=duration,
                videoId=str(row.get("videoId") or ""),
                cover=row.get("coverUrl") or "",
                fileUri="",
                views=_format_views(int(row.get("viewCount") or 0)),
                isLocal=False,
            )
        )
    return {"songs": songs, "playlist": [], "authors": [], "nextPageToken": None}


@router.get(
    "/search",
    summary="Search songs (and authors on first page)",
    description=(
        "Returns `data` with songs, playlists metadata, optionally paginated playlists, "
        "and up to five popular channel matches in `data.authors` "
        "(empty when `pageToken` is set)."
    ),
)
async def search_songs(
    q: str,
    pageToken: Optional[str] = None,
    return_playlists: Optional[bool] = Query(
        False, description="Include playlist results"),
    playlistPageTokens: Optional[str] = Query(
        "{}", description="JSON string of map of playlistId -> pageToken for pagination")
):
    try:
        # Parse playlistPageTokens from JSON string
        playlist_tokens_dict = json.loads(playlistPageTokens)
    except Exception:
        playlist_tokens_dict = {}

    used_fallback = False
    results: Optional[Dict[str, Any]] = None

    if _SEARCH_BACKEND == "youtube_api":
        try:
            results = await asyncio.wait_for(
                get_song_by_string(user_input=q, page_token=pageToken),
                timeout=_SEARCH_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            log.warning(
                "YouTube Data API search exceeded %.0fs — using yt-dlp fallback",
                _SEARCH_TIMEOUT_SECONDS,
            )
        except YouTubeQuotaExceededError as e:
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "QUOTA_EXCEEDED",
                    "message": str(e),
                    "solution": "Please try again tomorrow or contact administrator"
                }
            ) from e
        except YouTubeAccessDeniedError as e:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "ACCESS_DENIED",
                    "message": str(e),
                    "solution": "Check your YouTube API key configuration"
                }
            ) from e
        except YouTubeAPIError as e:
            log.warning(
                "YouTube Data API search failed (%s) — using yt-dlp fallback", e)

    if not results or not results.get("songs"):
        # Default backend, and fallback for the API path: fast local yt-dlp search.
        results = await run_in_threadpool(_ytdlp_fallback_results, q)
        used_fallback = True

    playlists_data: List[Dict[str, Any]] = []
    if return_playlists and not used_fallback:
        try:
            playlists = await asyncio.wait_for(
                get_playlist_search(q), timeout=_SEARCH_TIMEOUT_SECONDS
            )
            for pl in playlists:
                playlist_id = pl["id"]["playlistId"]
                token_for_this_playlist = playlist_tokens_dict.get(playlist_id)

                songs_data = await asyncio.wait_for(
                    get_playlist_songs_paginated(
                        playlist_id,
                        page_token=token_for_this_playlist,
                        page_size=10
                    ),
                    timeout=_SEARCH_TIMEOUT_SECONDS,
                )

                playlists_data.append({
                    "playlist": pl,
                    "songs": songs_data["songs"],
                    "nextPageToken": songs_data.get("nextPageToken")
                })
        except Exception:
            # Playlists are optional extras: never fail the whole search for them.
            log.warning("Playlist search failed/timed out — returning songs only")

    return {
        "success": True,
        "data": results,
        "playlists": playlists_data
    }
