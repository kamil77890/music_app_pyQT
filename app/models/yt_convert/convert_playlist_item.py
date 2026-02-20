from typing import Dict, Any
from app.logic.api_handler.handle_playlist_search import get_playlist_item_count


async def convert_playlist_meta(playlist: Dict[str, Any], idx: int) -> Dict[str, Any]:
    snippet = playlist.get("snippet", {})
    thumbnails = snippet.get("thumbnails", {})

    playlist_id = (
        playlist.get("id", {}).get("playlistId")
        or playlist.get("id")
        or f"playlist-{idx}"
    )

    title = snippet.get("title", "Unknown Playlist").replace("&amp;", "&")
    artist = snippet.get(
        "channelTitle", "Unknown Channel").replace("&amp;", "&")
    cover = thumbnails.get("high", {}).get("url", "")

    songs = await get_playlist_item_count(playlist_id)

    return {
        "id": playlist_id,
        "title": title,
        "artist": artist,
        "duration": 0,
        "videoId": playlist_id,
        "cover": cover,
        "songs": songs,
        "views": "",
        "fileUri": "",
        "isLocal": False,
        "isPlaylist": True,
    }
