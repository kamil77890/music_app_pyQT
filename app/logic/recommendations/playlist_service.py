import json
from pathlib import Path
from app.config.stałe import Parameters


_CACHE = {"path": None, "mtime": None, "songs": []}


def get_playlist_path():
    return Path(Parameters.get_download_dir()) / "All Songs" / "playlist.json"


def load_playlist():
    path = get_playlist_path()

    if not path.is_file():
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