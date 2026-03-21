from __future__ import annotations

from typing import Dict, Any, List, Optional
import asyncio
from googleapiclient.errors import HttpError

from app.exceptions.youtube_errors import YouTubeAPIError
from app.logic.api_handler.handle_playlist_search import get_playlist_search
from app.models.yt_convert.convert_playlist_item import convert_playlist_meta
from app.logic.api_handler.handle_yt_service import create_youtube_service
from app.utils.youtube_error_handler import youtube_api_error_handler
from app.models.yt_convert.convert_video_item import convert_video_item as convert_youtube_item_to_song


@youtube_api_error_handler
async def get_detailed_data(songs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not songs:
        return []

    song_ids = ",".join(song["id"]["videoId"] for song in songs)
    youtube = create_youtube_service()

    try:
        video_response = youtube.videos().list(
            part="snippet,contentDetails,statistics",
            id=song_ids
        ).execute()

        return video_response.get("items", [])

    except HttpError as e:
        raise YouTubeAPIError(f"YouTube API HTTP Error: {e}", e)
    except Exception as e:
        raise YouTubeAPIError(f"Error fetching song details: {e}", e)


@youtube_api_error_handler
async def get_video_by_id(video_id: str) -> Optional[Dict[str, Any]]:
    """Direct video lookup by YouTube video ID — no search quota burn."""
    if not video_id or not video_id.strip():
        return None
    youtube = create_youtube_service()
    resp = youtube.videos().list(
        part="snippet,contentDetails,statistics",
        id=video_id,
    ).execute()
    items = resp.get("items", [])
    if not items:
        return None
    return items[0]


@youtube_api_error_handler
async def get_song_by_string(user_input: str, page_token: str = None) -> Dict[str, Any]:
    if not user_input.strip():
        return {"songs": [], "playlist": [], "nextPageToken": None}

    youtube = create_youtube_service()

    search_response = youtube.search().list(
        q=user_input,
        part='snippet',
        maxResults=10,
        type='video',
        pageToken=page_token
    ).execute()

    songs = search_response.get("items", [])
    next_page_token = search_response.get("nextPageToken")

    detailed_songs = await get_detailed_data(songs)

    formatted_songs = [
        convert_youtube_item_to_song(item, idx)
        for idx, item in enumerate(detailed_songs)
    ]

    formatted_playlists = []
    if not page_token:
        playlists = await get_playlist_search(user_input)
        formatted_playlists = await asyncio.gather(*[
            convert_playlist_meta(item, idx)
            for idx, item in enumerate(playlists)
        ])

    return {
        "songs": formatted_songs,
        "playlist": formatted_playlists,
        "nextPageToken": next_page_token
    }