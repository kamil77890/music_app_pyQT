
from typing import List, Dict, Any
from urllib.parse import urlparse, parse_qs

class PreviewManager:
    """Manages song preview operations"""
    
    @staticmethod
    def extract_playlist_id(url: str) -> str:
        """Extract playlist ID from URL"""
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        playlist_id = qs.get("list")
        return playlist_id[0] if playlist_id else None
    
    @staticmethod
    def clean_video_id(video_id: str) -> str:
        """Clean video ID from various formats"""
        if not video_id:
            return None
        
        # Clean ID
        if len(video_id) == 11 and all(c.isalnum() or c in '_-' for c in video_id):
            return video_id
        
        # Handle URLs
        if "youtube.com" in video_id or "youtu.be" in video_id:
            try:
                parsed = urlparse(video_id)
                if parsed.hostname == "youtu.be":
                    return parsed.path[1:] if parsed.path.startswith('/') else parsed.path
                
                qs = parse_qs(parsed.query)
                if 'v' in qs:
                    return qs['v'][0]
            except Exception:
                pass
        
        return video_id