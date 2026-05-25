import json
import logging
from pathlib import Path
from app.config.stałe import Parameters

log = logging.getLogger(__name__)

_CACHE = {"path": None, "mtime": None, "songs": []}


def get_playlist_path():
    return Path(Parameters.get_download_dir()) / "All Songs" / "playlist.json"


def load_playlist():
    path = get_playlist_path()

    if not path.is_file():
        log.info("playlist.json missing — running library scan fallback")
        try:
            from app.logic.library_scanner import ensure_playlist_and_db
            data = ensure_playlist_and_db()
            songs = data.get("songs", [])
            if path.is_file():
                _CACHE.update({
                    "path": str(path),
                    "mtime": path.stat().st_mtime,
                    "songs": songs,
                })
            return songs
        except Exception:
            log.exception("Library scan fallback failed")
            return []

    mtime = path.stat().st_mtime

    if _CACHE["path"] == str(path) and _CACHE["mtime"] == mtime:
        return _CACHE["songs"]

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        songs = data.get("songs", [])
    except Exception:
        songs = []

    _CACHE.update({
        "path": str(path),
        "mtime": mtime,
        "songs": songs
    })

    return songs