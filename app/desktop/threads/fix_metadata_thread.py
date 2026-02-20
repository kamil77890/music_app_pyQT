import os
import re
import asyncio
import aiohttp
from typing import List, Dict, Optional
from PyQt5.QtCore import QThread, pyqtSignal

from mutagen.id3 import ID3, TIT2, TPE1, TALB, TCON, APIC, ID3NoHeaderError
from mutagen.mp4 import MP4, MP4Cover
from mutagen.mp3 import MP3
from mutagen.easyid3 import EasyID3

from app.logic.api_handler.handle_yt import get_song_by_string


class FixMetadataThread(QThread):
    progress = pyqtSignal(int, int, str)  # current, total, filename
    complete = pyqtSignal(list)  # results list
    error = pyqtSignal(str)  # error message
    
    def __init__(self, songs_data: List[Dict]):
        super().__init__()
        self.songs_data = songs_data
        self._stop = False
        
    def stop(self):
        self._stop = True
        
    def run(self):
        results = []
        total = len(self.songs_data)
        
        # Use asyncio to run async functions in thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        for idx, song_data in enumerate(self.songs_data):
            if self._stop:
                break
                
            file_path = song_data.get("file_path")
            fetch_covers = song_data.get("fetch_covers", True)
            overwrite = song_data.get("overwrite", False)
            
            self.progress.emit(idx + 1, total, os.path.basename(file_path))
            
            result = {
                "file_path": file_path,
                "success": False,
                "error": None
            }
            
            try:
                # Get file extension
                ext = os.path.splitext(file_path)[1].lower()
                
                if ext == ".mp3":
                    success = loop.run_until_complete(
                        self.fix_mp3_metadata(file_path, fetch_covers, overwrite)
                    )
                elif ext in [".mp4", ".m4a"]:
                    success = loop.run_until_complete(
                        self.fix_mp4_metadata(file_path, fetch_covers, overwrite)
                    )
                else:
                    result["error"] = f"Unsupported format: {ext}"
                    results.append(result)
                    continue
                    
                result["success"] = success
                
            except Exception as e:
                result["error"] = str(e)
                print(f"Error fixing metadata for {file_path}: {e}")
            
            results.append(result)
        
        loop.close()
        self.complete.emit(results)
    
    async def fix_mp3_metadata(self, file_path: str, fetch_covers: bool = True, overwrite: bool = False) -> bool:
        """Fix metadata for MP3 file."""
        try:
            # Read existing metadata
            existing_title = None
            existing_artist = None
            existing_video_id = None
            existing_cover_data = None
            existing_cover_mime = None
            
            try:
                id3 = ID3(file_path)
                existing_title = id3.get("TIT2")
                existing_artist = id3.get("TPE1")
                existing_video_id_frame = id3.get("TCON")
                if existing_video_id_frame and existing_video_id_frame.text:
                    existing_video_id = existing_video_id_frame.text[0]
                
                # Get existing cover
                apics = id3.getall('APIC')
                if apics and apics[0].data:
                    existing_cover_data = apics[0].data
                    existing_cover_mime = getattr(apics[0], 'mime', 'image/jpeg')
                    print(f"[FIX] Found existing cover ({len(existing_cover_data)} bytes)")
            except ID3NoHeaderError:
                id3 = ID3()
            except Exception as e:
                print(f"[FIX] Error reading existing metadata: {e}")
                id3 = ID3()
            
            # Try to find videoId
            video_id = None
            if existing_video_id and len(existing_video_id) == 11:
                video_id = existing_video_id
            else:
                # Try to find from filename
                video_id = await self._find_videoid_from_filename(file_path)
            
            # Get data from YouTube if we have videoId
            title = None
            artist = None
            thumbnail_url = None
            
            if video_id:
                try:
                    song_data = await get_song_by_string(video_id)
                    if song_data and isinstance(song_data, list) and len(song_data) > 0:
                        snippet = song_data[0].get("snippet", {})
                        title = snippet.get("title")
                        artist = snippet.get("channelTitle")
                        thumbnails = snippet.get("thumbnails", {})
                        # Get the highest quality thumbnail
                        thumbnail_url = (thumbnails.get("maxres", {}).get("url") or
                                       thumbnails.get("standard", {}).get("url") or
                                       thumbnails.get("high", {}).get("url") or
                                       thumbnails.get("medium", {}).get("url"))
                        print(f"[FIX] Found YouTube data: {title} - {artist}")
                except Exception as e:
                    print(f"[FIX] Failed to fetch YouTube metadata: {e}")
            
            # Use existing data if not overwriting
            if not overwrite:
                if existing_title and existing_title.text and not title:
                    title = existing_title.text[0]
                if existing_artist and existing_artist.text and not artist:
                    artist = existing_artist.text[0]
            
            # Fallback: title/artist from filename
            if not title or not artist:
                base = os.path.basename(file_path).rsplit(".mp3", 1)[0]
                if " - " in base:
                    parts = base.split(" - ", 1)
                    if len(parts) == 2:
                        artist, title = [p.strip() for p in parts]
                    else:
                        title = base
                        artist = "Unknown Artist"
                else:
                    title = base
                    artist = "Unknown Artist"
            
            # Clean up title
            title = self._clean_title(title)
            
            # Update text tags
            if title:
                id3.delall('TIT2')
                id3.add(TIT2(encoding=3, text=title))
            if artist:
                id3.delall('TPE1')
                id3.add(TPE1(encoding=3, text=artist))
            if video_id:
                id3.delall('TCON')
                id3.add(TCON(encoding=3, text=video_id))
            
            # Handle cover
            cover_data = existing_cover_data
            cover_mime = existing_cover_mime
            
            if fetch_covers:
                if (overwrite or not cover_data) and thumbnail_url:
                    try:
                        cover_data, cover_mime = await self._download_cover(thumbnail_url)
                    except Exception as e:
                        print(f"[FIX] Failed to download cover: {e}")
            
            # Add cover if we have one
            if cover_data and (overwrite or not existing_cover_data):
                try:
                    # Remove all existing APIC frames
                    id3.delall('APIC')
                    
                    # Add new APIC frame
                    apic = APIC(
                        encoding=3,
                        mime=cover_mime or 'image/jpeg',
                        type=3,  # Cover (front)
                        desc='Cover',
                        data=cover_data
                    )
                    id3.add(apic)
                    print(f"[FIX] Added cover ({len(cover_data)} bytes)")
                except Exception as e:
                    print(f"[FIX] Failed to add cover: {e}")
            
            # Save metadata
            id3.save(file_path, v2_version=3, v1=2)
            print(f"[FIX] ✅ Fixed metadata for {os.path.basename(file_path)}")
            return True
            
        except Exception as e:
            print(f"[FIX] ❌ Error fixing MP3 metadata: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def fix_mp4_metadata(self, file_path: str, fetch_covers: bool = True, overwrite: bool = False) -> bool:
        """Fix metadata for MP4 file."""
        try:
            audio = MP4(file_path)
            
            # Read existing metadata
            existing_title = audio.get("\xa9nam", [None])[0] if "\xa9nam" in audio else None
            existing_artist = audio.get("\xa9ART", [None])[0] if "\xa9ART" in audio else None
            existing_video_id = audio.get("\xa9cmt", [None])[0] if "\xa9cmt" in audio else None
            
            # Try to find videoId
            video_id = None
            if existing_video_id and len(existing_video_id) == 11:
                video_id = existing_video_id
            else:
                video_id = await self._find_videoid_from_filename(file_path)
            
            # Get data from YouTube if we have videoId
            title = None
            artist = None
            thumbnail_url = None
            
            if video_id:
                try:
                    song_data = await get_song_by_string(video_id)
                    if song_data and isinstance(song_data, list) and len(song_data) > 0:
                        snippet = song_data[0].get("snippet", {})
                        title = snippet.get("title")
                        artist = snippet.get("channelTitle")
                        thumbnails = snippet.get("thumbnails", {})
                        thumbnail_url = (thumbnails.get("maxres", {}).get("url") or
                                       thumbnails.get("standard", {}).get("url") or
                                       thumbnails.get("high", {}).get("url") or
                                       thumbnails.get("medium", {}).get("url"))
                except Exception as e:
                    print(f"[FIX] Failed to fetch YouTube metadata: {e}")
            
            # Use existing data if not overwriting
            if not overwrite:
                if existing_title and not title:
                    title = existing_title
                if existing_artist and not artist:
                    artist = existing_artist
            
            # Fallback: title/artist from filename
            if not title or not artist:
                base = os.path.basename(file_path).rsplit(".mp4", 1)[0]
                if " - " in base:
                    parts = base.split(" - ", 1)
                    if len(parts) == 2:
                        artist, title = [p.strip() for p in parts]
                    else:
                        title = base
                        artist = "Unknown Artist"
                else:
                    title = base
                    artist = "Unknown Artist"
            
            # Clean up title
            title = self._clean_title(title)
            
            # Update text tags
            if title:
                audio["\xa9nam"] = title
            if artist:
                audio["\xa9ART"] = artist
            if video_id:
                audio["\xa9cmt"] = video_id
            
            # Handle cover
            if fetch_covers and thumbnail_url:
                try:
                    cover_data, _ = await self._download_cover(thumbnail_url)
                    
                    # Determine format
                    if thumbnail_url.lower().endswith('.png'):
                        cover = MP4Cover(cover_data, MP4Cover.FORMAT_PNG)
                    else:
                        cover = MP4Cover(cover_data, MP4Cover.FORMAT_JPEG)
                    
                    audio["covr"] = [cover]
                    print(f"[FIX] Added cover to MP4 ({len(cover_data)} bytes)")
                except Exception as e:
                    print(f"[FIX] Failed to add cover to MP4: {e}")
            
            # Save metadata
            audio.save()
            print(f"[FIX] ✅ Fixed metadata for {os.path.basename(file_path)}")
            return True
            
        except Exception as e:
            print(f"[FIX] ❌ Error fixing MP4 metadata: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def _find_videoid_from_filename(self, file_path: str) -> Optional[str]:
        """Try to find videoId from filename."""
        base = os.path.basename(file_path)
        # Extract possible YouTube ID from filename (11 character alphanumeric)
        match = re.search(r'([A-Za-z0-9_-]{11})', base)
        if match:
            return match.group(1)
        return None
    
    def _clean_title(self, title: str) -> str:
        """Clean up title by removing common YouTube suffixes."""
        if not title:
            return title
        
        # Remove common YouTube suffixes
        patterns = [
            r'\s*\[.*?\]',  # [Official Video]
            r'\s*\(.*?\)',  # (Official Audio)
            r'\s*【.*?】',   # 【Japanese brackets】
            r'\s*[|•].*',   # | Official Audio etc
            r'\s*ft\.\s.*', # ft. Artist
            r'\s*feat\.\s.*', # feat. Artist
            r'\s*-\s*Official.*', # - Official Video
            r'\s*-\s*Lyrics.*',  # - Lyrics
            r'\s*-\s*Audio.*',   # - Audio
            r'\s*-\s*Video.*',   # - Video
            r'\s*HD$',           # HD
            r'\s*HQ$',           # HQ
            r'\s*4K$',           # 4K
        ]
        
        for pattern in patterns:
            title = re.sub(pattern, '', title, flags=re.IGNORECASE)
        
        return title.strip()
    
    async def _download_cover(self, url: str) -> tuple[bytes, str]:
        """Download cover image from URL."""
        import aiohttp
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                response.raise_for_status()
                data = await response.read()
                
                # Determine MIME type
                content_type = response.headers.get('content-type', 'image/jpeg')
                if 'png' in content_type:
                    mime_type = 'image/png'
                elif 'gif' in content_type:
                    mime_type = 'image/gif'
                else:
                    mime_type = 'image/jpeg'
                
                return data, mime_type