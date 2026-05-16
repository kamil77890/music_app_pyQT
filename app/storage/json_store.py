import json
import os
import threading
from contextlib import contextmanager
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
DATA_DIR.mkdir(exist_ok=True)

_lock = threading.Lock()

SUBSCRIPTIONS_FILE = "subscriptions.json"
NOTIFICATIONS_FILE = "notifications.json"
SEEN_VIDEO_IDS_FILE = "seen_video_ids.json"


def _default_for(filename: str):
    return {} if filename.endswith("dict.json") else []


def _read_path(path: Path, filename: str):
    if not path.exists():
        return _default_for(filename)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_path(path: Path, data: dict | list) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def read(filename: str) -> dict | list:
    path = DATA_DIR / filename
    with _lock:
        return _read_path(path, filename)


def write(filename: str, data: dict | list) -> None:
    path = DATA_DIR / filename
    with _lock:
        _write_path(path, data)


@contextmanager
def locked():
    _lock.acquire()
    try:
        yield
    finally:
        _lock.release()


def read_unlocked(filename: str) -> dict | list:
    path = DATA_DIR / filename
    return _read_path(path, filename)


def write_unlocked(filename: str, data: dict | list) -> None:
    path = DATA_DIR / filename
    _write_path(path, data)
