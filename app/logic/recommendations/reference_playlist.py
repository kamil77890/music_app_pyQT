from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urlparse

import yt_dlp

from app.storage import json_store

log = logging.getLogger(__name__)

REFERENCE_FILE = "recommendation_reference_playlist_dict.json"
DEFAULT_LIMIT = 100

_YTDLP_OPTS = {
    "quiet": True,
    "skip_download": True,
    "extract_flat": "in_playlist",
    "ignoreerrors": True,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _playlist_url(value: str) -> str:
    value = (value or "").strip()
    if not value:
        raise ValueError("Playlist URL is required")
    if value.startswith(("http://", "https://")):
        return value
    return f"https://www.youtube.com/playlist?list={value}"


def _playlist_id(url: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if query.get("list"):
        return query["list"][0]
    return ""


def _entry_to_item(entry: dict[str, Any]) -> dict[str, Any] | None:
    vid = entry.get("id") or entry.get("url")
    if not vid:
        return None
    title = entry.get("title") or ""
    if not title or title == "[Deleted video]":
        return None
    return {
        "videoId": str(vid),
        "title": title,
        "artist": entry.get("channel") or entry.get("uploader") or entry.get("uploader_id") or "",
        "channelId": entry.get("channel_id") or entry.get("uploader_id") or "",
        "url": f"https://www.youtube.com/watch?v={vid}",
    }


def extract_reference_playlist(url: str, *, limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
    normalized = _playlist_url(url)
    try:
        with yt_dlp.YoutubeDL(_YTDLP_OPTS) as ydl:
            data = ydl.extract_info(normalized, download=False)
    except Exception as exc:
        log.exception("Reference playlist extraction failed")
        raise ValueError(f"Could not read playlist: {exc}") from exc

    entries = data.get("entries") or []
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        item = _entry_to_item(entry)
        if not item:
            continue
        vid = item["videoId"]
        if vid in seen:
            continue
        seen.add(vid)
        items.append(item)
        if len(items) >= limit:
            break

    if not items:
        raise ValueError("Playlist contains no readable videos")

    return {
        "url": normalized,
        "playlistId": _playlist_id(normalized),
        "title": data.get("title") or "Reference playlist",
        "updatedAt": _now_iso(),
        "itemCount": len(items),
        "items": items,
    }


def save_reference_playlist(url: str, *, limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
    playlist = extract_reference_playlist(url, limit=limit)
    json_store.write(REFERENCE_FILE, playlist)
    return playlist


def get_reference_playlist() -> dict[str, Any]:
    data = json_store.read(REFERENCE_FILE)
    return data if isinstance(data, dict) else {}


def clear_reference_playlist() -> None:
    json_store.write(REFERENCE_FILE, {})
