from __future__ import annotations

import os
from typing import Any

import requests

from app.config.jellyfin_config import JellyfinConfig


def fetch_jellyfin_music_items() -> dict[str, Any]:
    api_key = JellyfinConfig.get_jellyfin_api_key()
    base_url = JellyfinConfig.get_jellyfin_url().rstrip("/")
    if not api_key:
        return {"enabled": False, "items": [], "message": "JELLYFIN_API_KEY not configured"}
    try:
        resp = requests.get(
            f"{base_url}/Items",
            params={"Recursive": "true", "IncludeItemTypes": "Audio", "Fields": "Path,Genres,Tags,Album,Artists"},
            headers={"X-Emby-Token": api_key},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        return {"enabled": True, "items": data.get("Items", []), "message": "ok"}
    except requests.RequestException as exc:
        return {"enabled": True, "items": [], "message": str(exc)}


def match_jellyfin_item_to_local_song(song: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any] | None:
    song_path = os.path.realpath(song.get("path") or "")
    for item in items:
        item_path = os.path.realpath(item.get("Path") or item.get("path") or "")
        if song_path and item_path and song_path == item_path:
            return item
    title = (song.get("title") or "").strip().lower()
    artist = (song.get("artist") or "").strip().lower()
    for item in items:
        item_title = (item.get("Name") or "").strip().lower()
        artists = " ".join(item.get("Artists") or []).lower()
        if title and title == item_title and (not artist or artist in artists):
            return item
    return None


def compare_jellyfin_metadata(local_song: dict[str, Any], jellyfin_item: dict[str, Any] | None) -> dict[str, Any]:
    if not jellyfin_item:
        return {"matched": False, "differences": ["missing_in_jellyfin"]}
    differences = []
    local_genre = local_song.get("primary_genre") or local_song.get("genre")
    jf_genres = jellyfin_item.get("Genres") or []
    if local_genre and local_genre not in jf_genres:
        differences.append("genre")
    local_album = local_song.get("album")
    jf_album = jellyfin_item.get("Album")
    if local_album and jf_album and local_album != jf_album:
        differences.append("album")
    return {"matched": True, "differences": differences}
