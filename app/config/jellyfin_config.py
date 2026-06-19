import os
import logging

log = logging.getLogger(__name__)


class JellyfinConfig:
    """Jellyfin music library settings, read from environment on every call.

    Follows the same pattern as ``Parameters`` in ``stałe.py`` — values are
    always read fresh from ``os.environ`` so a server restart is not required
    when the env file changes.
    """

    @classmethod
    def _get(cls, key: str, default: str) -> str:
        return os.environ.get(key, default)

    @classmethod
    def get_music_library_path(cls) -> str:
        return cls._get("MUSIC_LIBRARY_PATH", "/srv/music")

    @classmethod
    def get_music_library_owner(cls) -> str:
        return cls._get("MUSIC_LIBRARY_OWNER", "")

    @classmethod
    def get_music_library_group(cls) -> str:
        return cls._get("MUSIC_LIBRARY_GROUP", "media")

    @classmethod
    def get_output_format(cls) -> str:
        return cls._get("MUSIC_OUTPUT_FORMAT", "keep")

    @classmethod
    def get_output_bitrate(cls) -> str:
        return cls._get("MUSIC_OUTPUT_BITRATE", "320k")

    @classmethod
    def get_jellyfin_url(cls) -> str:
        return cls._get("JELLYFIN_URL", "http://localhost:8096")

    @classmethod
    def get_jellyfin_api_key(cls) -> str:
        return cls._get("JELLYFIN_API_KEY", "")

    @classmethod
    def get_jellyfin_auto_scan(cls) -> bool:
        val = cls._get("JELLYFIN_AUTO_SCAN", "true")
        return val.lower() in ("true", "1", "yes")

    @classmethod
    def get_keep_legacy_copy(cls) -> bool:
        val = cls._get("MUSIC_KEEP_LEGACY_COPY", "false")
        return val.lower() in ("true", "1", "yes")

    @classmethod
    def get_temp_path(cls) -> str:
        return cls._get("MUSIC_TEMP_PATH", "").strip()

    @classmethod
    def get_temp_dir(cls) -> str:
        temp = cls.get_temp_path()
        if temp:
            return temp
        from app.config.stałe import Parameters
        return os.path.join(Parameters.get_download_dir(), ".tmp")
