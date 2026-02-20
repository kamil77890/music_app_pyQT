"""
Helper functions
"""

import os
import asyncio
from typing import Dict, Any, Optional
from urllib.parse import urlparse, parse_qs
from app.desktop.utils.async_runner import AsyncRunner



"""
Utility functions for the desktop application
"""

import os
import re
import json
from typing import Dict, Any, Optional, Union
from pathlib import Path


def song_to_dict(song) -> Dict[str, Any]:
    """
    Convert a song object (Pydantic model or dict) to a dictionary.
    """
    if isinstance(song, dict):
        return song
    elif hasattr(song, 'dict'):
        # Pydantic model
        return song.dict()
    elif hasattr(song, '__dict__'):
        # Regular object
        return song.__dict__
    else:
        return {}


def get_field(data, field: str, default=None):
    """
    Safely get a field from data that could be a dict, Pydantic model, or object.
    """
    if hasattr(data, field):
        return getattr(data, field, default)
    elif isinstance(data, dict):
        return data.get(field, default)
    else:
        return default



def get_audio_files_recursive(directory: str, extensions: tuple = ('.mp3', '.mp4', '.m4a')) -> list:
    """Get all audio files recursively from directory."""
    audio_files = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.lower().endswith(extensions):
                audio_files.append(os.path.join(root, file))
    return audio_files

# For backward compatibility
def get_mp3_files_recursive(directory: str) -> list:
    """Get all MP3 files recursively from directory."""
    return get_audio_files_recursive(directory, ('.mp3',))




def clean_filename(filename: str) -> str:
    """Clean a filename by removing invalid characters"""
    if not filename:
        return "Unknown"
    
    # Replace invalid characters with spaces or remove them
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, ' ')
    
    # Remove multiple spaces
    filename = ' '.join(filename.split())
    
    # Limit length
    if len(filename) > 100:
        filename = filename[:100]
    
    return filename.strip()

def clean_video_id(video_id: str) -> Optional[str]:
    """Extract clean video ID from various formats"""
    if not video_id:
        return None
    
    # If it's already a clean ID (11 characters, YouTube format)
    if len(video_id) == 11 and all(c.isalnum() or c in '_-' for c in video_id):
        return video_id
    
    # Handle URLs
    if "youtube.com" in video_id or "youtu.be" in video_id:
        try:
            parsed = urlparse(video_id)
            
            # Short URL format (youtu.be/VIDEO_ID)
            if parsed.hostname == "youtu.be":
                return parsed.path[1:] if parsed.path.startswith('/') else parsed.path
            
            # Standard URL format
            qs = parse_qs(parsed.query)
            if 'v' in qs:
                return qs['v'][0]
        except Exception:
            pass
    
    return video_id