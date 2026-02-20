
import ssl
import time
from typing import Optional
from app.logic.api_handler.handle_yt import get_song_by_string

def safe_get_song_by_string(videoId: str, retries: int = 3, backoff: float = 1.0) -> Optional[list]:
    attempt = 0
    while attempt < retries:
        try:
            return get_song_by_string(videoId)
        except ssl.SSLError as e:
            print(f"[safe_get] SSL error ({attempt+1}/{retries}): {e}")
        except Exception as e:
            print(f"[safe_get] Error ({attempt+1}/{retries}): {e}")

        attempt += 1    
        time.sleep(backoff * (2 ** (attempt - 1)))

    return None
