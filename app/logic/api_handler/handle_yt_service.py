import os

import httplib2
from googleapiclient.discovery import build

from app.utils.api_key_manager import api_key_manager

# Connection/read timeout for YouTube Data API calls. Without this, a stalled
# TCP connect (e.g. SYN-SENT to a Google edge) can hang the request forever.
_YOUTUBE_API_TIMEOUT_SECONDS = float(
    os.environ.get("YOUTUBE_API_TIMEOUT_SECONDS", "8")
)


def create_youtube_service():
    current_key = api_key_manager.get_current_key()
    http = httplib2.Http(timeout=_YOUTUBE_API_TIMEOUT_SECONDS)
    return build("youtube", "v3", developerKey=current_key, http=http)
