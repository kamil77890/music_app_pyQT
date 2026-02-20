from yt_dlp import YoutubeDL
from functools import lru_cache
import os

COOKIE_FILE = os.path.join(os.path.dirname(__file__), "cookies.txt")


@lru_cache(maxsize=1024)
def fetch_info(video_id: str):
    vid_url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'cookiefile': COOKIE_FILE if os.path.exists(COOKIE_FILE) else None,
        'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
        'headers': {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
        },
        'quiet': True,
        'no_warnings': True,
    }
    with YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(vid_url, download=False)
