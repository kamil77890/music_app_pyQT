from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any

from app.db import subscription_repository as store
from app.logic.api_handler.handle_yt_service import create_youtube_service
from app.logic.recommendations.music_filter import is_short
from app.utils.youtube_error_handler import youtube_api_error_handler

log = logging.getLogger(__name__)

VIDEOS_PER_CHANNEL = 5

# Uploads playlist id for a channel never changes -> cache for the process life.
_uploads_playlist_cache: dict[str, str] = {}

# Short-lived cache of fetched uploads so /feed and the poller don't re-hit the API.
_FEED_CACHE_TTL = 900  # 15 minutes
_channel_videos_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def _playlist_item_to_feed_item(item: dict[str, Any]) -> dict[str, Any]:
    snippet = item.get("snippet", {})
    resource = snippet.get("resourceId", {})
    video_id = resource.get("videoId", "")
    thumbs = snippet.get("thumbnails", {}) or {}
    cover = (
        thumbs.get("maxres", {}).get("url")
        or thumbs.get("high", {}).get("url")
        or f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"
    )
    return {
        "videoId": video_id,
        "title": snippet.get("title", ""),
        "channelId": snippet.get("channelId", "") or snippet.get("videoOwnerChannelId", ""),
        "channelTitle": snippet.get("channelTitle", "") or snippet.get("videoOwnerChannelTitle", ""),
        "cover": cover,
        "publishedAt": snippet.get("publishedAt", ""),
        "duration": 0,
        "views": "",
    }


@youtube_api_error_handler
def _resolve_uploads_playlists(channel_ids: list[str]) -> dict[str, str]:
    """Map channelId -> uploads playlist id (1 quota unit per 50 channels)."""
    missing = [c for c in channel_ids if c and c not in _uploads_playlist_cache]
    youtube = create_youtube_service()
    for i in range(0, len(missing), 50):
        chunk = missing[i : i + 50]
        resp = youtube.channels().list(
            part="contentDetails",
            id=",".join(chunk),
            maxResults=50,
        ).execute()
        for item in resp.get("items", []):
            cid = item.get("id")
            uploads = (
                item.get("contentDetails", {})
                .get("relatedPlaylists", {})
                .get("uploads")
            )
            if cid and uploads:
                _uploads_playlist_cache[cid] = uploads
    return {c: _uploads_playlist_cache[c] for c in channel_ids if c in _uploads_playlist_cache}


@youtube_api_error_handler
def fetch_channel_videos(
    channel_id: str, max_results: int = VIDEOS_PER_CHANNEL
) -> list[dict[str, Any]]:
    """Recent uploads for a channel via the cheap uploads playlist (1 unit)."""
    cached = _channel_videos_cache.get(channel_id)
    if cached and time.time() - cached[0] < _FEED_CACHE_TTL:
        return cached[1][:max_results]

    uploads = _resolve_uploads_playlists([channel_id]).get(channel_id)
    if not uploads:
        return []

    youtube = create_youtube_service()
    resp = youtube.playlistItems().list(
        part="snippet",
        playlistId=uploads,
        maxResults=min(max_results, 50),
    ).execute()
    items = [
        _playlist_item_to_feed_item(it)
        for it in resp.get("items", [])
        if it.get("snippet", {}).get("resourceId", {}).get("videoId")
    ]
    _channel_videos_cache[channel_id] = (time.time(), items)
    return items[:max_results]


def process_new_videos(videos: list[dict[str, Any]]) -> int:
    return store.process_new_videos(videos)


def _decode_page_token(page_token: str | None) -> int:
    if not page_token:
        return 0
    try:
        data = json.loads(base64.urlsafe_b64decode(page_token.encode()).decode())
        return int(data.get("offset", 0))
    except (json.JSONDecodeError, ValueError, TypeError):
        return 0


def _encode_page_token(offset: int) -> str:
    return base64.urlsafe_b64encode(json.dumps({"offset": offset}).encode()).decode()


def _collect_all_uploads(
    subscriptions: list[dict[str, Any]], per_channel: int
) -> list[dict[str, Any]]:
    """Fetch uploads for every subscription, warming the playlist-id cache once."""
    channel_ids = [s.get("channelId") for s in subscriptions if s.get("channelId")]
    _resolve_uploads_playlists(channel_ids)  # one batched channels.list

    all_videos: list[dict[str, Any]] = []
    for cid in channel_ids:
        try:
            for v in fetch_channel_videos(cid, per_channel):
                if not is_short(title=v.get("title", "")):
                    all_videos.append(v)
        except Exception:
            log.exception("Failed to fetch uploads for channel %s", cid)
    return all_videos


def build_subscription_feed(
    max_results: int = 20,
    page_token: str | None = None,
) -> dict[str, Any]:
    subscriptions: list[dict[str, Any]] = store.list_subscriptions()
    if not subscriptions:
        return {"items": [], "nextPageToken": None}

    all_videos = _collect_all_uploads(subscriptions, VIDEOS_PER_CHANNEL)
    all_videos.sort(key=lambda v: v.get("publishedAt", ""), reverse=True)
    process_new_videos(all_videos)

    offset = _decode_page_token(page_token)
    page = all_videos[offset : offset + max_results]
    next_offset = offset + max_results
    next_page_token = _encode_page_token(next_offset) if next_offset < len(all_videos) else None

    return {"items": page, "nextPageToken": next_page_token}


def run_subscription_poll() -> None:
    subscriptions: list[dict[str, Any]] = store.list_subscriptions()
    if not subscriptions:
        return
    all_videos = _collect_all_uploads(subscriptions, VIDEOS_PER_CHANNEL)
    if all_videos:
        process_new_videos(all_videos)
