import json
import os
import re
import logging
from typing import Optional
from urllib.parse import urlparse, parse_qs

from fastapi import APIRouter, HTTPException, Query
from googleapiclient.errors import HttpError

from app.config.stałe import Parameters
from app.logic.color_extractor import extract_color_palette
from app.logic.api_handler.handle_playlist_search import get_playlist_songs_paginated
from app.logic.api_handler.handle_yt_service import create_youtube_service
from app.models.yt_convert.convert_video_item import convert_video_item as convert_youtube_item_to_song

log = logging.getLogger(__name__)

router = APIRouter(tags=["Playlists"])


def _extract_playlist_id(value: str) -> str:
    """Extract YouTube playlist ID from a URL or raw ID string."""
    raw = value.strip()

    # Already a valid-looking playlist ID
    if re.match(r"^(PL|UU|LL|RD|RDMM|OL)[A-Za-z0-9_-]+$", raw):
        return raw

    try:
        parsed = urlparse(raw)
    except Exception:
        raise HTTPException(status_code=400, detail="Nieprawidłowy URL playlisty")

    hostname = parsed.hostname or ""
    if "youtube.com" in hostname or "youtu.be" in hostname:
        qs = parse_qs(parsed.query)
        if "list" in qs:
            return qs["list"][0]

    raise HTTPException(status_code=400, detail="Nie znaleziono ID playlisty w podanym URL")


@router.get("/playlist")
async def get_playlist(
    url: str = Query(..., description="YouTube playlist URL lub playlist_id"),
    pageToken: Optional[str] = Query(None, description="Token do paginacji"),
):
    """Pobiera playlistę z YouTube i zwraca strukturę identyczną jak /search.

    Klient frontendowy normalizuje odpowiedź przez normalizePlaylistUrlResponse
    która odczytuje json.playlists[0].songs.
    """
    playlist_id = _extract_playlist_id(url)

    try:
        youtube = create_youtube_service()
        pl_response = youtube.playlists().list(
            part="snippet,contentDetails",
            id=playlist_id,
        ).execute()
    except HttpError as e:
        raise HTTPException(
            status_code=e.resp.status,
            detail=f"Błąd YouTube API: {e}",
        )

    pl_items = pl_response.get("items", [])
    if not pl_items:
        raise HTTPException(status_code=404, detail="Playlista nie znaleziona")

    pl_data = pl_items[0]
    snippet = pl_data.get("snippet", {})
    thumbs = snippet.get("thumbnails", {}) or {}

    playlist_meta = {
        "id": playlist_id,
        "title": (snippet.get("title") or "Unknown Playlist").replace("&amp;", "&"),
        "artist": (snippet.get("channelTitle") or "Unknown Channel").replace("&amp;", "&"),
        "duration": 0,
        "videoId": playlist_id,
        "cover": thumbs.get("high", {}).get("url") or thumbs.get("medium", {}).get("url") or "",
        "songs": (pl_data.get("contentDetails") or {}).get("itemCount", 0),
        "views": "",
        "fileUri": "",
        "isLocal": False,
        "isPlaylist": True,
    }

    songs_data = await get_playlist_songs_paginated(
        playlist_id,
        page_token=pageToken,
        page_size=50,
    )

    formatted_songs = [
        convert_youtube_item_to_song(item, idx)
        for idx, item in enumerate(songs_data.get("songs", []))
    ]

    return {
        "success": True,
        "data": {
            "songs": formatted_songs,
            "playlist": [playlist_meta],
            "authors": [],
            "nextPageToken": songs_data.get("nextPageToken"),
        },
        "playlists": [
            {
                "id": playlist_id,
                "videoId": playlist_id,
                "title": playlist_meta["title"],
                "artist": playlist_meta["artist"],
                "cover": playlist_meta["cover"],
                "songs": formatted_songs,
                "nextPageToken": songs_data.get("nextPageToken"),
                "isPlaylist": True,
            }
        ],
    }


def _count_filled_fields(song: dict) -> int:
    """Counts how many meaningful fields a song entry has."""
    filled = 0
    for key, value in song.items():
        if value is None or value == "":
            continue
        if isinstance(value, bool):
            filled += 1
        elif isinstance(value, (int, float)):
            filled += 1
        elif isinstance(value, str) and value.strip():
            filled += 1
        elif isinstance(value, dict):
            filled += 1
        elif isinstance(value, list):
            filled += 1
    return filled


def _deduplicate_songs(data: dict) -> dict:
    """Removes duplicate songs keeping the one with more filled fields.

    Duplicates are detected by matching 'title' + 'artist' (case-insensitive).
    When both entries have the same number of filled fields, the first one is removed.
    """
    songs = data.get("songs", [])
    seen: dict[str, list[int]] = {}

    for idx, song in enumerate(songs):
        key = f"{song.get('title', '').strip().lower()}||{song.get('artist', '').strip().lower()}"
        if key and key != "||":
            seen.setdefault(key, []).append(idx)

    to_remove = set()
    for indices in seen.values():
        if len(indices) < 2:
            continue

        # Score each duplicate by filled field count
        scored = [(i, _count_filled_fields(songs[i])) for i in indices]
        # Sort: highest score first, then by index (prefer later index on tie)
        scored.sort(key=lambda x: (x[1], -x[0]), reverse=True)

        # Keep the best one, remove the rest
        best_idx = scored[0][0]
        for idx_entry in scored[1:]:
            to_remove.add(idx_entry[0])

    # Build new list preserving order
    data["songs"] = [
        song for idx, song in enumerate(songs) if idx not in to_remove
    ]

    if to_remove:
        log.info("Removed %d duplicate song(s) from playlist", len(to_remove))

    return data


def _enrich_songs_with_colors(songs: list) -> list:
    """Add dominantColor and colorPalette from cover if available."""
    for song in songs:
        if song.get("cover"):
            try:
                color_data = extract_color_palette(song["cover"])
                song["dominantColor"] = color_data.get("dominantColor")
                song["colorPalette"] = color_data.get("colorPalette")
            except Exception as e:
                log.warning(f"Could not extract colors for {song.get('title')}: {e}")
                song["dominantColor"] = None
                song["colorPalette"] = None
        else:
            song["dominantColor"] = None
            song["colorPalette"] = None
    
    return songs


def _inject_lyrics(songs: list[dict]) -> list[dict]:
    """Add lyrics to songs that are missing them, reading from sidecar files."""
    from app.logic.library_scanner import _read_lyrics

    out: list[dict] = []
    for s in songs:
        if s.get("lyrics"):
            out.append(s)
            continue
        fp = s.get("path", "")
        fn = s.get("filename", "")
        if fp and fn:
            lyrics = _read_lyrics(fp, fn)
            s = dict(s)
            s["lyrics"] = lyrics
        out.append(s)
    return out


@router.get("/playlists/all-songs")
def get_all_songs_playlist():
    """Zwraca całą zawartość pliku playlist.json z folderu 'All Songs' z usuniętymi duplikatami i kolorami okładek."""
    download_dir = Parameters.get_download_dir()
    playlist_folder = os.path.join(download_dir, "All Songs")
    playlist_file = os.path.join(playlist_folder, "playlist.json")

    if not os.path.isfile(playlist_file):
        raise HTTPException(
            status_code=404,
            detail=f"Playlist 'All Songs' nie istnieje: {playlist_file}"
        )

    try:
        with open(playlist_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        data = _deduplicate_songs(data)
        data["songs"] = _enrich_songs_with_colors(data.get("songs", []))
        return data
    except json.JSONDecodeError as e:
        log.error("Błąd parsowania playlist.json: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Nieprawidłowy format JSON w playlist.json: {str(e)}"
        )
    except OSError as e:
        log.error("Błąd odczytu playlist.json: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Nie można odczytać playlist.json: {str(e)}"
        )


@router.post("/playlists/rescan")
def rescan_library():
    """Wymuś ponowny skan katalogu z muzyką.

    Nadpisuje istniejący playlist.json i synchronizuje nowe utwory z DB.
    """
    from app.logic.library_scanner import scan_music_files, build_and_save_playlist, sync_songs_to_db

    songs = scan_music_files()
    data = build_and_save_playlist(songs)
    inserted = sync_songs_to_db(songs)

    return {
        "scanned": len(songs),
        "inserted_to_db": inserted,
        "playlist_path": str(Parameters.get_download_dir() + "/All Songs/playlist.json"),
    }
