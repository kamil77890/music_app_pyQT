from __future__ import annotations

import base64
import json
import logging
from typing import Any
from app.db import subscription_repository as store
from app.logic.api_handler.handle_yt_service import create_youtube_service
from app.utils.youtube_error_handler import youtube_api_error_handler

log = logging.getLogger(__name__)

VIDEOS_PER_CHANNEL = 5


def _search_item_to_feed_item(item: dict[str, Any]) -> dict[str, Any]:
    snippet = item.get("snippet", {})
    video_id = item.get("id", {}).get("videoId", "")
    channel_id = snippet.get("channelId", "")
    return {
        "videoId": video_id,
        "title": snippet.get("title", ""),
        "channelId": channel_id,
        "channelTitle": snippet.get("channelTitle", ""),
        "cover": f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg",
        "publishedAt": snippet.get("publishedAt", ""),
        "duration": 0,
        "views": "",
    }


@youtube_api_error_handler
def fetch_channel_videos(channel_id: str, max_results: int = VIDEOS_PER_CHANNEL) -> list[dict[str, Any]]:
    youtube = create_youtube_service()
    resp = youtube.search().list(
        channelId=channel_id,
        order="date",
        type="video",
        part="snippet",
        maxResults=max_results,
    ).execute()
    items = resp.get("items", [])
    return [_search_item_to_feed_item(item) for item in items if item.get("id", {}).get("videoId")]


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


def build_subscription_feed(
    max_results: int = 20,
    page_token: str | None = None,
) -> dict[str, Any]:
    subscriptions: list[dict[str, Any]] = store.list_subscriptions()
    if not subscriptions:
        return {"items": [], "nextPageToken": None}

    all_videos: list[dict[str, Any]] = []
    for sub in subscriptions:
        channel_id = sub.get("channelId")
        if not channel_id:
            continue
        try:
            all_videos.extend(fetch_channel_videos(channel_id, VIDEOS_PER_CHANNEL))
        except Exception:
            log.exception("Failed to fetch feed for channel %s", channel_id)
            raise

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

    all_videos: list[dict[str, Any]] = []
    for sub in subscriptions:
        channel_id = sub.get("channelId")
        if not channel_id:
            continue
        try:
            all_videos.extend(fetch_channel_videos(channel_id, VIDEOS_PER_CHANNEL))
        except Exception:
            log.exception("Poll failed for channel %s", channel_id)

    if all_videos:
        process_new_videos(all_videos)
