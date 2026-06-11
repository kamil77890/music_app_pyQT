import json
import os
from pathlib import Path

from app.logic.atomic import atomic_write_json

DEFAULT_COLOR_DATA = {
    "dominantColor": None,
    "colorPalette": None,
}


def _cache_dir() -> Path:
    directory = Path(os.environ.get("DATA_DIR", "./data")) / "cache"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _cache_path() -> Path:
    return _cache_dir() / "colors.json"


def load_color_cache() -> dict:
    path = _cache_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_color_cache(cache: dict) -> None:
    atomic_write_json(_cache_path(), cache)


def get_cached_color(cover: str | None) -> dict | None:
    if not cover:
        return None
    cache = load_color_cache()
    entry = cache.get(cover)
    if not isinstance(entry, dict):
        return None
    return {
        "dominantColor": entry.get("dominantColor"),
        "colorPalette": entry.get("colorPalette"),
    }


def set_cached_color(cover: str | None, color_data: dict) -> None:
    if not cover:
        return
    cache = load_color_cache()
    cache[cover] = {
        "dominantColor": color_data.get("dominantColor"),
        "colorPalette": color_data.get("colorPalette"),
    }
    save_color_cache(cache)


def get_or_compute_color(cover: str | None, compute) -> dict:
    if not cover:
        return DEFAULT_COLOR_DATA

    cached = get_cached_color(cover)
    if cached is not None:
        return cached

    color_data = compute()
    set_cached_color(cover, color_data)
    return color_data
