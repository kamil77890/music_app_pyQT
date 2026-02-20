"""
Audio playback management
"""

import os
from typing import List, Tuple

class AudioManager:
    """Manages audio playback queue"""
    
    def __init__(self):
        self.playlist: List[Tuple[str, dict]] = []  # (file_path, metadata)
        self.current_index = -1
    
    def add_to_playlist(self, file_path: str, metadata: dict = None):
        """Add song to playlist"""
        self.playlist.append((file_path, metadata))
        if self.current_index == -1:
            self.current_index = 0
    
    def get_current(self):
        """Get current song"""
        if 0 <= self.current_index < len(self.playlist):
            return self.playlist[self.current_index]
        return None
    
    def get_next(self):
        """Get next song in playlist"""
        if self.current_index < len(self.playlist) - 1:
            self.current_index += 1
            return self.playlist[self.current_index]
        return None
    
    def get_previous(self):
        """Get previous song in playlist"""
        if self.current_index > 0:
            self.current_index -= 1
            return self.playlist[self.current_index]
        return None
    
    def remove_from_playlist(self, index: int):
        """Remove song from playlist"""
        if 0 <= index < len(self.playlist):
            del self.playlist[index]
            if self.current_index >= index:
                self.current_index -= 1
                if self.current_index < 0 and self.playlist:
                    self.current_index = 0
    
    def clear_playlist(self):
        """Clear entire playlist"""
        self.playlist.clear()
        self.current_index = -1
    
    def move_up(self, index: int):
        """Move song up in playlist"""
        if index > 0 and index < len(self.playlist):
            self.playlist[index], self.playlist[index-1] = self.playlist[index-1], self.playlist[index]
            if self.current_index == index:
                self.current_index -= 1
            elif self.current_index == index - 1:
                self.current_index += 1
    
    def move_down(self, index: int):
        """Move song down in playlist"""
        if index >= 0 and index < len(self.playlist) - 1:
            self.playlist[index], self.playlist[index+1] = self.playlist[index+1], self.playlist[index]
            if self.current_index == index:
                self.current_index += 1
            elif self.current_index == index + 1:
                self.current_index -= 1