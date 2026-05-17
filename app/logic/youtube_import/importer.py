from __future__ import annotations

import logging
from typing import Any

import requests

from app.db import oauth_repository
from app.logic.youtube_import.oauth_flow import get_authenticated_headers

log = logging.getLogger(__name__)

YT_API = "https://www.googleapis.com/youtube/v3"


def _get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    headers = get_authenticated_headers()
    resp = requests.get(f"{YT_API}/{path}", params=params, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _import_liked(max_items: int = 100) -> list[dict[str, Any]]:
    """Import Liked Videos playlist (LL)."""
    items: list[dict[str, Any]] = []
    try:
        pl_resp = _get("playlistItems", {
            "part": "snippet,contentDetails",
            "playlistId": "LL",
            "maxResults": min(max_items, 50),
        })
    except requests.HTTPError as exc:
        log.warning("Liked playlist import failed: %s", exc)
        return items

    for it in pl_resp.get("items", []):
        vid = it.get("contentDetails", {}).get("videoId")
        sn = it.get("snippet", {})
        if not vid:
            continue
        items.append({
            "video_id": vid,
            "source": "liked",
            "title": sn.get("title"),
            "channel_id": sn.get("channelId"),
            "channel_title": sn.get("channelTitle"),
            "raw_meta": sn,
        })
    return items


def _import_subscriptions(max_items: int = 50) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    try:
        resp = _get("subscriptions", {
            "part": "snippet",
            "mine": "true",
            "maxResults": min(max_items, 50),
        })
    except requests.HTTPError as exc:
        log.warning("Subscriptions import failed: %s", exc)
        return items

    for it in resp.get("items", []):
        sn = it.get("snippet", {})
        cid = sn.get("resourceId", {}).get("channelId")
        if not cid:
            continue
        items.append({
            "video_id": cid,
            "source": "subscription_channel",
            "title": sn.get("title"),
            "channel_id": cid,
            "channel_title": sn.get("title"),
            "raw_meta": sn,
        })
    return items


def _import_playlist_items(playlist_id: str, source: str, max_items: int = 30) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    try:
        resp = _get("playlistItems", {
            "part": "snippet,contentDetails",
            "playlistId": playlist_id,
            "maxResults": min(max_items, 50),
        })
    except requests.HTTPError as exc:
        log.warning("Playlist %s import failed: %s", playlist_id, exc)
        return items

    for it in resp.get("items", []):
        vid = it.get("contentDetails", {}).get("videoId")
        sn = it.get("snippet", {})
        if not vid:
            continue
        items.append({
            "video_id": vid,
            "source": source,
            "title": sn.get("title"),
            "channel_id": sn.get("channelId"),
            "channel_title": sn.get("channelTitle"),
            "raw_meta": sn,
        })
    return items


def run_import() -> dict[str, Any]:
    if not oauth_repository.is_connected():
        raise RuntimeError("YouTube account not connected")

    all_items: list[dict[str, Any]] = []
    all_items.extend(_import_liked(100))

    try:
        pl_resp = _get("playlists", {
            "part": "snippet",
            "mine": "true",
            "maxResults": 10,
        })
        for pl in pl_resp.get("items", [])[:5]:
            pid = pl.get("id")
            title = (pl.get("snippet", {}).get("title") or "").lower()
            if not pid or pid == "LL":
                continue
            if "watch later" in title or "history" in title:
                src = "history" if "history" in title else "playlist"
            else:
                src = "playlist"
            all_items.extend(_import_playlist_items(pid, src, max_items=20))
    except requests.HTTPError:
        log.exception("User playlists import failed")

    video_items = [i for i in all_items if len(i.get("video_id", "")) == 11]
    n = oauth_repository.upsert_imported_items(video_items)
    oauth_repository.set_last_import()

    return {
        "imported": n,
        "sources": {
            "liked": sum(1 for i in video_items if i.get("source") == "liked"),
            "playlist": sum(1 for i in video_items if i.get("source") == "playlist"),
            "history": sum(1 for i in video_items if i.get("source") == "history"),
        },
    }
