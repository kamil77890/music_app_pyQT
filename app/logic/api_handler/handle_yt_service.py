from googleapiclient.discovery import build
from app.utils.api_key_manager import api_key_manager


def create_youtube_service():
    current_key = api_key_manager.get_current_key()
    return build('youtube', 'v3', developerKey=current_key)
