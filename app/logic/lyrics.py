import hashlib
import os
from pathlib import Path

from app.logic.atomic import atomic_write_text

LYRICS_EXTENSIONS = (".lrc", ".txt")


def _data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "./data"))


def _lyrics_dir() -> Path:
    directory = _data_dir() / "lyrics"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def song_identity(song: dict | str | None = None, **fallbacks) -> str:
    if isinstance(song, str):
        raw = song
    elif isinstance(song, dict):
        raw = str(song.get("songId") or song.get("id") or song.get("videoId") or "")
        if not raw:
            parts = [str(song.get("artist") or ""), str(song.get("title") or ""), str(song.get("path") or "")]
            raw = "||".join(parts) if any(parts) else ""
    else:
        raw = ""

    if raw:
        safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in raw)
        return safe[:180]

    parts = [
        str(fallbacks.get("songId") or fallbacks.get("id") or ""),
        str(fallbacks.get("videoId") or ""),
        str(fallbacks.get("artist") or ""),
        str(fallbacks.get("title") or ""),
        str(fallbacks.get("path") or ""),
    ]
    digest = hashlib.sha256("||".join(parts).encode("utf-8")).hexdigest()
    return digest


def normalize_ext(ext: str | None) -> str:
    normalized = (ext or ".txt").lower()
    if not normalized.startswith("."):
        normalized = f".{normalized}"
    if normalized not in LYRICS_EXTENSIONS:
        raise ValueError("Lyrics format must be '.lrc' or '.txt'")
    return normalized


def lyrics_path(song: dict | str | None = None, ext: str | None = ".lrc", **fallbacks) -> Path:
    return _lyrics_dir() / f"{song_identity(song, **fallbacks)}{normalize_ext(ext)}"


def existing_lyrics_path(song: dict | str | None = None, **fallbacks) -> Path | None:
    identity = song_identity(song, **fallbacks)
    directory = _lyrics_dir()
    for ext in LYRICS_EXTENSIONS:
        candidate = directory / f"{identity}{ext}"
        if candidate.is_file():
            return candidate
    return None


def read_lyrics(song: dict | str | None = None, include_text: bool = False, **fallbacks) -> dict:
    path = existing_lyrics_path(song, **fallbacks)
    if path is None:
        return {"hasLyrics": False, "lyricsPath": None, "lyricsFormat": None}

    result = {
        "hasLyrics": True,
        "lyricsPath": str(path),
        "lyricsFormat": path.suffix.lstrip("."),
    }
    if include_text:
        result["lyricsText"] = path.read_text(encoding="utf-8")
    return result


def save_lyrics(text: str, song: dict | str | None = None, ext: str = ".lrc", **fallbacks) -> Path:
    path = lyrics_path(song, ext=ext, **fallbacks)
    atomic_write_text(path, text.strip() + "\n")
    return path


def delete_lyrics(song: dict | str | None = None, **fallbacks) -> None:
    path = existing_lyrics_path(song, **fallbacks)
    if path is not None:
        path.unlink(missing_ok=True)
