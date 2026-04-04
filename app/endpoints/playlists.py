import json
import os
import logging
from fastapi import APIRouter, HTTPException
from app.config.stałe import Parameters

log = logging.getLogger(__name__)

router = APIRouter(tags=["Playlists"])


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


@router.get("/playlists/all-songs")
def get_all_songs_playlist():
    """Zwraca całą zawartość pliku playlist.json z folderu 'All Songs' z usuniętymi duplikatami."""
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
