"""
Thread for downloading songs
"""

import os
import traceback
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse, parse_qs
from PyQt5.QtCore import QThread, pyqtSignal

from app.desktop.utils.helpers import get_mp3_files_recursive, song_to_dict, get_field, clean_filename, clean_video_id
from app.desktop.utils.metadata import get_mp3_metadata
from app.desktop.logic.download_manager import DownloadManager
from app.logic.ultimate_downloader import download_song

class DownloadThread(QThread):
    """Thread for downloading songs"""
    progress = pyqtSignal(int, str, int, int)  # progress, song_title, current, total
    song_complete = pyqtSignal(dict, bool, str, str)  # song dict, success, file_path, error_message
    finished = pyqtSignal(list)
    error = pyqtSignal(str, object)
    
    def __init__(self, songs, download_path):
        super().__init__()
        self.songs = songs
        self.download_path = download_path
        self.download_manager = DownloadManager(download_path)
        
    def run(self):
        downloaded = []
        total = len(self.songs)
        
        for i, song in enumerate(self.songs):
            try:
                # Convert song to dictionary
                song_dict = song_to_dict(song)
                
                # Extract video ID from song object
                video_id = None
                for field in ["videoId", "id", "url"]:
                    video_id = get_field(song_dict, field)
                    if video_id:
                        break
                
                if not video_id:
                    title = get_field(song_dict, "title", "")
                    print(f"No video ID found for: {title}")
                    self.song_complete.emit(song_dict, False, "", "No video ID found")
                    continue
                
                # Clean video ID
                video_id = clean_video_id(video_id)
                
                if not video_id:
                    title = get_field(song_dict, "title", "Unknown")
                    print(f"Invalid video ID for song: {title}")
                    self.song_complete.emit(song_dict, False, "", "Invalid video ID")
                    continue
                
                title = get_field(song_dict, "title", "Unknown")
                artist = get_field(song_dict, "artist", "Unknown Artist")
                
                print(f"Downloading {i+1}/{total}: {title} - {artist}")
                

                try:
                    safe_title = clean_filename(title)
                    safe_artist = clean_filename(artist)
                    
                    # Download with proper filename handling
                    path = download_song(video_id, safe_title, format_ext="mp3")
                    
                    # Check if the downloaded file exists
                    if path and os.path.exists(path):
                        print(f"✓ Downloaded: {os.path.basename(path)}")
                        
                        # Try to rename to artist - title format
                        filename = f"{safe_artist} - {safe_title}.mp3"
                        actual_filename = os.path.basename(path)
                        if actual_filename != filename:
                            new_path = os.path.join(os.path.dirname(path), filename)
                            try:
                                if os.path.exists(new_path):
                                    os.remove(new_path)
                                os.rename(path, new_path)
                                path = new_path
                            except Exception as e:
                                print(f"Could not rename file: {e}")
                        
                        downloaded.append(path)
                        self.progress.emit(100, title, i+1, total)
                        self.song_complete.emit(song_dict, True, path, "")
                        
                        # Create a symbolic link
                        self.download_manager.create_song_link(path, video_id, title, artist)
                    else:
                        print(f"✗ Download failed: {title}")
                        self.progress.emit(100, title, i+1, total)
                        self.song_complete.emit(song_dict, False, "", "Download failed")
                        
                except Exception as e:
                    error_msg = f"Download error: {str(e)}"
                    print(f"✗ {error_msg}")
                    self.progress.emit(100, title, i+1, total)
                    self.song_complete.emit(song_dict, False, "", error_msg)
                    self.error.emit(str(e), song_dict)
                
                # Update overall progress
                progress_value = int((i + 1) / total * 100)
                
            except Exception as e:
                error_msg = f"Error processing song {i+1}: {str(e)}"
                print(error_msg)
                traceback.print_exc()
                self.error.emit(error_msg, song_dict if 'song_dict' in locals() else {"title": "Unknown"})
                self.song_complete.emit(song_dict if 'song_dict' in locals() else {"title": "Unknown"}, False, "", error_msg)
        
        self.finished.emit(downloaded)