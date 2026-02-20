"""
Download management core functionality
"""

import os
from typing import List, Dict, Any
from app.desktop.utils.helpers import get_mp3_files_recursive, clean_filename

class DownloadManager:
    """Manages download operations"""
    
    def __init__(self, download_path: str):
        self.download_path = download_path
        self.existing_songs_dir = "app/songs"
    
    
    def create_song_link(self, file_path: str, video_id: str, title: str, artist: str):
        """Create symbolic link for easy management"""
        try:
            os.makedirs(self.existing_songs_dir, exist_ok=True)
            
            safe_title = clean_filename(title)
            safe_artist = clean_filename(artist)
            link_name = f"{safe_artist} - {safe_title}.mp3"
            link_path = os.path.join(self.existing_songs_dir, link_name)
            
            # Create link
            try:
                if os.name == 'nt':
                    import shutil
                    if not os.path.exists(link_path):
                        shutil.copy2(file_path, link_path)
                else:
                    if not os.path.exists(link_path):
                        os.symlink(os.path.abspath(file_path), link_path)
            except Exception as e:
                print(f"Note: Could not create link: {e}")
                
        except Exception as e:
            print(f"Error creating song link: {e}")