from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List, Dict, Any
import json
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

router = APIRouter()


@router.get("/search")
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
    except:
        playlist_tokens_dict = {}

    try:
        results = await get_song_by_string(user_input=q, page_token=pageToken)

        playlists_data: List[Dict[str, Any]] = []
        if return_playlists:
            playlists = await get_playlist_search(q)
            for pl in playlists:
                playlist_id = pl["id"]["playlistId"]
                token_for_this_playlist = playlist_tokens_dict.get(playlist_id)

                songs_data = await get_playlist_songs_paginated(
                    playlist_id,
                    page_token=token_for_this_playlist,
                    page_size=10
                )

                playlists_data.append({
                    "playlist": pl,
                    "songs": songs_data["songs"],
                    "nextPageToken": songs_data.get("nextPageToken")
                })

        return {
            "success": True,
            "data": results,
            "playlists": playlists_data
        }

    except YouTubeQuotaExceededError as e:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "QUOTA_EXCEEDED",
                "message": str(e),
                "solution": "Please try again tomorrow or contact administrator"
            }
        )
    except YouTubeAccessDeniedError as e:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "ACCESS_DENIED",
                "message": str(e),
                "solution": "Check your YouTube API key configuration"
            }
        )
    except YouTubeAPIError as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "YOUTUBE_API_ERROR",
                "message": str(e),
                "solution": "Please try again later"
            }
        )
