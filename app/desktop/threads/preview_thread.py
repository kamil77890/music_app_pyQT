"""
Thread for fetching song previews with proper thread management
"""

import asyncio
import traceback
from typing import Dict, Any, Optional
from urllib.parse import urlparse, parse_qs
from PyQt5.QtCore import QThread, pyqtSignal, QMutex

from app.desktop.utils.async_runner import AsyncRunner
from app.logic.ultimate_downloader import download_song, download_playlist
from app.logic.downloader.retries import safe_get_song_by_string
from app.logic.api_handler.handle_playlist_search import get_playlist_songs_paginated
from app.models.yt_convert.convert_video_item import convert_video_item as convert_youtube_item_to_song


class PreviewThread(QThread):
    """Thread for fetching song previews with proper cleanup"""
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    
    def __init__(self, url: str):
        super().__init__()
        self.url = url
        self._is_running = False
        self._mutex = QMutex()
        
    def run(self):
        try:
            self._mutex.lock()
            self._is_running = True
            self._mutex.unlock()
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            data = loop.run_until_complete(self.fetch_preview(self.url))
            
            loop.close()
            
            if self._is_running:  # Only emit if not stopped
                self.finished.emit(data)
            
        except Exception as e:
            if self._is_running:  # Only emit if not stopped
                error_msg = f"Preview error: {str(e)}\n{traceback.format_exc()}"
                print(error_msg)
                self.error.emit(error_msg)
        finally:
            self._mutex.lock()
            self._is_running = False
            self._mutex.unlock()
    
    def stop(self):
        """Safely stop the thread"""
        self._mutex.lock()
        self._is_running = False
        self._mutex.unlock()
        
        if self.isRunning():
            self.quit()
            self.wait(1000)  # Wait up to 1 second for thread to finish
    
    async def fetch_preview(self, url: str) -> Dict[str, Any]:
        """Async method to fetch preview data"""
        url = url.strip()
        if not url:
            return {"songs": [], "playlist": [], "nextPageToken": None}
        
        # Check if we should stop
        self._mutex.lock()
        should_stop = not self._is_running
        self._mutex.unlock()
        
        if should_stop:
            return {"songs": [], "playlist": [], "nextPageToken": None}
        
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        playlist_id = qs.get("list")
        
        try:
            if playlist_id:
                # Handle playlist
                pid = playlist_id[0]
                songs_data = await get_playlist_songs_paginated(pid, page_size=50)
                raw_items = songs_data.get("songs", []) or []
                
                # Convert items to song format
                formatted_songs = []
                for idx, item in enumerate(raw_items):
                    # Check if we should stop
                    self._mutex.lock()
                    should_stop = not self._is_running
                    self._mutex.unlock()
                    
                    if should_stop:
                        break
                    
                    try:
                        song = convert_youtube_item_to_song(item, idx)
                        formatted_songs.append(song)
                    except Exception as e:
                        print(f"Error converting item {idx}: {e}")
                
                return {
                    "songs": formatted_songs, 
                    "playlist": [], 
                    "nextPageToken": songs_data.get("nextPageToken")
                }
            else:
                # Handle single song or search
                result = await safe_get_song_by_string(url)
                
                # Check if we should stop
                self._mutex.lock()
                should_stop = not self._is_running
                self._mutex.unlock()
                
                if should_stop:
                    return {"songs": [], "playlist": [], "nextPageToken": None}
                
                # Normalize result format
                if isinstance(result, list):
                    return {"songs": result, "playlist": [], "nextPageToken": None}
                elif isinstance(result, dict):
                    if "songs" in result:
                        return result
                    else:
                        return {"songs": [result], "playlist": [], "nextPageToken": None}
                else:
                    # Single song object
                    return {"songs": [result], "playlist": [], "nextPageToken": None}
                    
        except Exception as e:
            print(f"Error in fetch_preview: {e}")
            traceback.print_exc()
            return {"songs": [], "playlist": [], "nextPageToken": None}