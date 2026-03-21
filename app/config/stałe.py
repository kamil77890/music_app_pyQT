import os
from pathlib import Path

YT_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YT_PLAYLIST_ITEMS_URL = "https://www.googleapis.com/youtube/v3/playlistItems"


def _project_root() -> Path:
    """`app/config/stałe.py` → project root."""
    return Path(__file__).resolve().parents[2]


def _load_project_dotenv() -> None:
    """
    Load project root `.env` into `os.environ`.

    Does **not** override variables already set in the process environment.
    Called once when this module is imported so `API_KEY` from `.env` is
    visible before `APIKeyManager` is constructed.
    """
    env_path = _project_root() / ".env"
    if not env_path.is_file():
        return
    try:
        with open(env_path, encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                key = k.strip()
                val = v.strip().strip('"').strip("'").replace("\r", "")
                if key and key not in os.environ:
                    os.environ[key] = val
    except OSError:
        pass


_load_project_dotenv()


class Parameters:
    def __init__(self):
        self.download_dir = os.environ.get(
            'FILEPATH', os.path.join(os.getcwd(), 'app', 'songs'))
        self.json_file = os.environ.get(
            'JSONFILE', os.path.join(self.download_dir, 'songs.json'))
        self.subtitles_files = os.environ.get(
            'SUBTITLES_FILES', os.path.join(os.getcwd(), 'app', 'songs', 'subtitles'))

    @staticmethod
    def get_download_dir():
        return os.environ.get('FILEPATH', os.path.join(os.getcwd(), 'app', 'songs'))

    @staticmethod
    def get_subtitles_dir():
        return os.environ.get('SUBTITLES_FILES', os.path.join(os.getcwd(), 'app', 'songs', 'subtitles'))

    @staticmethod
    def get_json_file():
        return os.environ.get('JSONFILE', os.path.join(Parameters.get_download_dir(), 'songs.json'))

    @staticmethod
    def get_api_keys():
        """
        YouTube Data API keys. Primary: ``API_KEY``, ``API_KEY_2``, …

        If ``API_KEY`` is unset, these are tried for the first slot (in order):
        ``YOUTUBE_API_KEY``, ``YT_API_KEY``, ``GOOGLE_API_KEY``.
        """
        keys = []
        first = (
            os.environ.get("API_KEY", "").strip()
            or os.environ.get("YOUTUBE_API_KEY", "").strip()
            or os.environ.get("YT_API_KEY", "").strip()
            or os.environ.get("GOOGLE_API_KEY", "").strip()
        )
        if first:
            keys.append(first)
        for var in ("API_KEY_2", "API_KEY_3", "API_KEY_4"):
            k = os.environ.get(var, "").strip()
            if k and k not in keys:
                keys.append(k)
        if not keys:
            raise RuntimeError(
                "No YouTube API keys configured. "
                "Set API_KEY (or YOUTUBE_API_KEY) in project `.env` or the environment. "
                f"Expected file: {_project_root() / '.env'}"
            )
        return keys

    @staticmethod
    def get_active_api_key_index():
        return int(os.environ.get('ACTIVE_API_KEY_INDEX', '0'))

    @staticmethod
    def set_active_api_key_index(index: int):
        os.environ['ACTIVE_API_KEY_INDEX'] = str(index)

    @staticmethod
    def get_active_api_key():
        keys = Parameters.get_api_keys()
        active_index = Parameters.get_active_api_key_index()
        return keys[active_index]

    @staticmethod
    def switch_to_next_api_key():
        keys = Parameters.get_api_keys()
        current_index = Parameters.get_active_api_key_index()
        next_index = (current_index + 1) % len(keys)
        Parameters.set_active_api_key_index(next_index)
        return next_index

    @staticmethod
    def get_yt_search_url():
        return YT_SEARCH_URL

    @staticmethod
    def get_yt_playlist_items_url():
        return YT_PLAYLIST_ITEMS_URL
