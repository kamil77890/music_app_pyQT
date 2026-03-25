"""
Configuration management for the desktop application
"""

import os
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

# Jedna biblioteka: domyślnie pusto — wszystko pod download_path (np. …/songs + «All Songs»).
DEFAULT_LIBRARY_SCAN_EXTRA_PATHS: List[str] = []

# Domyślny katalog: pobrania MP3, playlisty i folder «All Songs».
DEFAULT_DOWNLOAD_PATH = str(Path.home() / "Music" / "YT Music")

DEFAULT_CONFIG = {
    "download_path": DEFAULT_DOWNLOAD_PATH,
    "library_scan_extra_paths": list(DEFAULT_LIBRARY_SCAN_EXTRA_PATHS),
    "api_base_url": "http://127.0.0.1:8001",
    "window_size": [1200, 800],
    "window_position": [100, 100],
    "volume": 70,
    "loop_enabled": True,
    "player_visible": True,
    "youtube_api_key": "AIzaSyD-GhNz8WyvqiuDgtj7Qt_r-GsnGR1mN5Q", 
    "theme": "dark",
    "download_quality": "high",
    "auto_download": False,
    "max_concurrent_downloads": 3
}

CONFIG_FILE = Path.home() / ".yt-music-downloader" / "config.json"


class Config:
    """Configuration manager"""
    
    def __init__(self):
        self.config = DEFAULT_CONFIG.copy()
        self.load()
    
    def load(self):
        """Load configuration from file"""
        try:
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, 'r') as f:
                    saved_config = json.load(f)
                    self.config.update(saved_config)
        except Exception as e:
            print(f"Error loading config: {e}")
    
    def save(self):
        """Save configuration to file"""
        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value"""
        return self.config.get(key, default)
    
    def set(self, key: str, value: Any):
        """Set a configuration value"""
        self.config[key] = value
        self.save()
    
    def get_download_path(self) -> str:
        """Get the download path, create if it doesn't exist"""
        path = self.get("download_path", DEFAULT_CONFIG["download_path"])
        os.makedirs(path, exist_ok=True)
        return path

    def get_library_scan_extra_paths(self) -> List[str]:
        """Absolutne ścieżki poza głównym download_path — skanowane przy imporcie do «All Songs»."""
        raw = self.config.get("library_scan_extra_paths")
        if raw is None:
            raw = DEFAULT_LIBRARY_SCAN_EXTRA_PATHS
        if not isinstance(raw, list):
            return list(DEFAULT_LIBRARY_SCAN_EXTRA_PATHS)
        out: List[str] = []
        for p in raw:
            s = str(p).strip()
            if s:
                out.append(s)
        return out

    def get_youtube_api_key(self) -> str:
        """Get YouTube API key"""
        return self.get("youtube_api_key", "")


config = Config()