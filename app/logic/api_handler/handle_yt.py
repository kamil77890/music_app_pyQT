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
async def get_top_related_channels(
    user_input: str, *, limit: int = 5, search_pool: int = 18
) -> List[Dict[str, Any]]:
    """
    YouTube channels semantically tied to `user_input`, ranked by popularity
    (subscriber count, then uploads, then channel view count).
    """
    if not user_input.strip():
        return []

    yt = create_youtube_service()
    sr = yt.search().list(
        q=user_input,
        part="snippet",
        type="channel",
        maxResults=min(search_pool, 50),
        order="relevance",
    ).execute()

    channel_ids: List[str] = []
    seen: set[str] = set()
    for item in sr.get("items", []):
        cid = item.get("id", {}).get("channelId")
        if cid and cid not in seen:
            seen.add(cid)
            channel_ids.append(cid)

    if not channel_ids:
        return []

    cr = yt.channels().list(
        part="snippet,statistics",
        id=",".join(channel_ids),
        maxResults=50,
    ).execute()

    rows: List[Dict[str, Any]] = []
    for ch in cr.get("items", []):
        cid = ch.get("id") or ""
        snip = ch.get("snippet", {}) or {}
        stats = ch.get("statistics", {}) or {}
        thumbs = snip.get("thumbnails", {}) or {}
        thumb_url = (
            thumbs.get("high", {}).get("url")
            or thumbs.get("medium", {}).get("url")
            or thumbs.get("default", {}).get("url")
            or ""
        )

        subs_raw = stats.get("subscriberCount")
        subscriber_count = int(subs_raw) if subs_raw is not None else 0
        hidden_subs = bool(stats.get("hiddenSubscriberCount"))

        video_count = int(stats.get("videoCount", 0) or 0)
        view_count = int(stats.get("viewCount", 0) or 0)

        rows.append(
            {
                "channelId": cid,
                "title": (snip.get("title") or "").replace("&amp;", "&"),
                "thumbnail": thumb_url,
                "customUrl": snip.get("customUrl"),
                "subscriberCount": subscriber_count,
                "hiddenSubscriberCount": hidden_subs,
                "videoCount": video_count,
                "channelViewCount": view_count,
            }
        )

    rows.sort(
        key=lambda r: (
            r["subscriberCount"],
            r["videoCount"],
            r["channelViewCount"],
        ),
        reverse=True,
    )
    return rows[:limit]


@youtube_api_error_handler
async def get_song_by_string(user_input: str, page_token: str = None) -> Dict[str, Any]:
    if not user_input.strip():
        return {"songs": [], "playlist": [], "authors": [], "nextPageToken": None}

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

    if page_token:
        detailed_songs = await get_detailed_data(songs)
        formatted_playlists = []
        authors: List[Dict[str, Any]] = []
    else:
        playlists = await get_playlist_search(user_input)
        detailed_songs, playlist_metas, authors = await asyncio.gather(
            get_detailed_data(songs),
            asyncio.gather(
                *[convert_playlist_meta(item, idx) for idx, item in enumerate(playlists)]
            ),
            get_top_related_channels(user_input),
        )
        formatted_playlists = list(playlist_metas)

    formatted_songs = [
        convert_youtube_item_to_song(item, idx)
        for idx, item in enumerate(detailed_songs)
    ]

    return {
        "songs": formatted_songs,
        "playlist": formatted_playlists,
        "authors": authors,
        "nextPageToken": next_page_token
    }