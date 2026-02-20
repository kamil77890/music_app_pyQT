from typing import Optional, List, Dict, Any
from googleapiclient.errors import HttpError

from app.exceptions.youtube_errors import (
    YouTubeQuotaExceededError,
    YouTubeAccessDeniedError,
    YouTubeAPIError,
)
from app.utils.youtube_error_handler import youtube_api_error_handler
from app.logic.api_handler.handle_yt_service import create_youtube_service


async def get_playlist_songs_paginated(
    playlist_id: str,
    page_token: Optional[str] = None,
    page_size: int = 10
) -> Dict[str, Any]:
    youtube = create_youtube_service()

    response = youtube.playlistItems().list(
        part="snippet,contentDetails",
        playlistId=playlist_id,
        maxResults=page_size,
        pageToken=page_token
    ).execute()

    items = response.get("items", [])
    video_ids = [item["contentDetails"]["videoId"] for item in items]

    detailed_videos = await get_songs_from_playlist(
        [{"id": {"videoId": vid}} for vid in video_ids]
    )

    return {
        "songs": detailed_videos,
        "nextPageToken": response.get("nextPageToken")
    }


@youtube_api_error_handler
async def get_songs_from_playlist(songs) -> List[Dict[str, Any]]:

    if not songs:
        return []

    song_ids = ",".join(song["id"]["videoId"] for song in songs)
    youtube = create_youtube_service()

    try:
        video_response = youtube.videos().list(
            part="snippet,contentDetails",
            id=song_ids
        ).execute()

        return video_response.get("items", [])

    except HttpError as e:
        raise
    except Exception as e:
        raise YouTubeAPIError(f"Error fetching detailed song data: {e}", e)





@youtube_api_error_handler
async def get_playlist_search(query: str) -> List[Dict[str, Any]]:
    if not query.strip():
        return []

    youtube = create_youtube_service()

    try:
        search_response = youtube.search().list(
            q=query,
            part="snippet",
            maxResults=3,
            type="playlist"
        ).execute()

        return search_response.get("items", [])

    except HttpError as e:
        raise
    except Exception as e:
        raise YouTubeAPIError(
            f"Error fetching playlist search results: {e}", e)


async def get_playlist_item_count(playlist_id: str) -> int:
    youtube = create_youtube_service()
    try:
        response = youtube.playlists().list(
            part="contentDetails",
            id=playlist_id
        ).execute()

        items = response.get("items", [])
        if not items:
            return 0
        return items[0]["contentDetails"]["itemCount"]

    except HttpError:
        return 0
