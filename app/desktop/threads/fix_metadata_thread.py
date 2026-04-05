"""
FixMetadataThread — background worker that fixes title, artist, and cover art
for local audio files using YouTube API data (via video ID) or filename parsing.
"""
import logging
import os
import re
import asyncio
from typing import List, Dict, Optional

import aiohttp
from PyQt5.QtCore import QThread, pyqtSignal

log = logging.getLogger(__name__)

from mutagen.id3 import ID3, TIT2, TPE1, TCON, APIC, ID3NoHeaderError
from mutagen.mp4 import MP4, MP4Cover
from mutagen.mp3 import MP3
from mutagen.easyid3 import EasyID3

from app.desktop.utils.playlist_manager import PlaylistManager


class FixMetadataThread(QThread):
    progress = pyqtSignal(int, int, str)   # current, total, filename
    complete = pyqtSignal(list)            # results list
    error    = pyqtSignal(str)

    def __init__(self, songs_data: List[Dict], playlist_folder: Optional[str] = None):
        super().__init__()
        self.songs_data = songs_data
        self.playlist_folder = playlist_folder  # Path to playlist folder for JSON sync
        self._stop = False

    def stop(self):
        self._stop = True

    def _sync_to_playlist_json(self, results: List[Dict]):
        """
        Sync fixed metadata from audio files to playlist.json
        (Audio files -> JSON direction)
        Uses verify_metadata from add_metadata.py for consistent metadata extraction
        """
        if not self.playlist_folder or not os.path.isdir(self.playlist_folder):
            return

        try:
            playlist_data = PlaylistManager.get_playlist_info(self.playlist_folder)
            songs = playlist_data.get("songs", [])
            updated_count = 0

            for result in results:
                if not result.get("success"):
                    continue

                file_path = result.get("file_path", "")
                if not file_path:
                    continue

                # Find matching song in playlist by file path
                for song in songs:
                    song_path = song.get("file_path") or song.get("path", "")
                    if os.path.normcase(os.path.abspath(song_path)) == os.path.normcase(os.path.abspath(file_path)):
                        # Use verify_metadata from add_metadata.py for consistent extraction
                        from app.logic.metadata.add_metadata import verify_metadata
                        ext = os.path.splitext(file_path)[1].lstrip(".").lower()
                        metadata = verify_metadata(file_path, ext)

                        if metadata:
                            # Update playlist.json with verified metadata
                            song["title"] = metadata.get("title", song.get("title"))
                            song["artist"] = metadata.get("artist", song.get("artist"))
                            song["videoId"] = metadata.get("videoId", song.get("videoId", ""))
                            song["cover"] = metadata.get("cover", "")
                            song["has_cover"] = metadata.get("has_cover", False)

                            updated_count += 1
                            log.info("Synced %s to playlist.json", os.path.basename(file_path))
                        break

            # Save updated playlist
            if updated_count > 0:
                playlist_data["modified"] = os.path.getctime(self.playlist_folder)
                json_path = os.path.join(self.playlist_folder, "playlist.json")
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(playlist_data, f, indent=2, ensure_ascii=False)
                log.info("Synced %d songs to playlist.json", updated_count)

        except Exception as e:
            log.error("Error syncing to playlist.json: %s", e)

    # ── entry point ────────────────────────────────────────────

    def run(self):
        results = []
        total = len(self.songs_data)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Load playlist.json data for JSON -> Audio sync
        playlist_songs_map = {}
        if self.playlist_folder and os.path.isdir(self.playlist_folder):
            try:
                playlist_data = PlaylistManager.get_playlist_info(self.playlist_folder)
                for song in playlist_data.get("songs", []):
                    song_path = song.get("file_path") or song.get("path", "")
                    if song_path:
                        # Normalize path for matching
                        normalized = os.path.normcase(os.path.abspath(song_path))
                        playlist_songs_map[normalized] = song
                log.info("Loaded %d songs from playlist.json for sync", len(playlist_songs_map))
            except Exception as e:
                log.warning("Failed to load playlist.json: %s", e)

        for idx, song_data in enumerate(self.songs_data):
            if self._stop:
                break

            file_path    = song_data.get("file_path") or song_data.get("path", "")
            fetch_covers = song_data.get("fetch_covers", True)
            overwrite    = song_data.get("overwrite", False)
            # New: if use_json_only is True, skip YouTube and only use playlist.json data
            use_json_only = song_data.get("use_json_only", False)

            self.progress.emit(idx + 1, total, os.path.basename(file_path))

            result = {"file_path": file_path, "success": False, "error": None}

            # Get playlist JSON data for this file (if exists)
            normalized_path = os.path.normcase(os.path.abspath(file_path))
            json_metadata = playlist_songs_map.get(normalized_path)

            # If use_json_only is True and we have JSON metadata, sync directly
            if use_json_only and json_metadata:
                try:
                    ext = os.path.splitext(file_path)[1].lower()
                    # Use JSON metadata to fix audio file directly
                    if ext == ".mp3":
                        ok = loop.run_until_complete(
                            self._fix_mp3_from_json(file_path, json_metadata, fetch_covers, overwrite))
                    elif ext in (".mp4", ".m4a"):
                        ok = loop.run_until_complete(
                            self._fix_mp4_from_json(file_path, json_metadata, fetch_covers, overwrite))
                    else:
                        result["error"] = f"Unsupported format: {ext}"
                        results.append(result)
                        continue
                    result["success"] = ok
                    result["source"] = "playlist.json"
                except Exception as e:
                    result["error"] = str(e)
                    log.error("Error fixing from JSON %s: %s", file_path, e)
            else:
                # Original behavior: use YouTube API
                try:
                    ext = os.path.splitext(file_path)[1].lower()
                    if ext == ".mp3":
                        ok = loop.run_until_complete(
                            self._fix_mp3(file_path, fetch_covers, overwrite, json_metadata))
                    elif ext in (".mp4", ".m4a"):
                        ok = loop.run_until_complete(
                            self._fix_mp4(file_path, fetch_covers, overwrite, json_metadata))
                    else:
                        result["error"] = f"Unsupported format: {ext}"
                        results.append(result)
                        continue
                    result["success"] = ok
                    result["source"] = "youtube"
                except Exception as e:
                    result["error"] = str(e)
                    log.error("Error fixing %s: %s", file_path, e)

            results.append(result)

        # Sync results to playlist.json (Audio files -> JSON)
        self._sync_to_playlist_json(results)

        loop.close()
        self.complete.emit(results)

    # ── YouTube helpers ────────────────────────────────────────

    async def _fetch_youtube(self, video_id: Optional[str], search_query: str = ""):
        """
        Returns (title, artist, thumbnail_url, found_video_id) from YouTube.

        Strategy:
          1. If we have a video_id → direct lookup (cheap, no search quota)
          2. Fallback → search by video_id string
          3. If no video_id at all → search by title+artist from filename
        """
        # 1) Direct lookup by ID
        if video_id:
            try:
                from app.logic.api_handler.handle_yt import get_video_by_id
                item = await get_video_by_id(video_id)
                if item:
                    snippet = item.get("snippet", {})
                    thumbs  = snippet.get("thumbnails", {})
                    thumb   = (
                        thumbs.get("maxres",   {}).get("url")
                        or thumbs.get("standard", {}).get("url")
                        or thumbs.get("high",     {}).get("url")
                        or thumbs.get("medium",   {}).get("url")
                    )
                    title  = snippet.get("title")
                    artist = snippet.get("channelTitle")
                    log.info("YouTube (direct): %s - %s", title, artist)
                    return title, artist, thumb, video_id
            except Exception as e:
                log.warning("Direct lookup failed: %s", e)

        # 2) Search — use video_id as query, or fall back to title+artist
        query = video_id or search_query
        if not query:
            return None, None, None, None

        try:
            from app.logic.api_handler.handle_yt import get_song_by_string
            data = await get_song_by_string(query)
            songs = data.get("songs", [])
            if songs:
                s = songs[0]
                title  = getattr(s, "title",  None) or (s.get("title")  if isinstance(s, dict) else None)
                artist = getattr(s, "artist", None) or (s.get("artist") if isinstance(s, dict) else None)
                cover  = getattr(s, "cover",  None) or (s.get("cover")  if isinstance(s, dict) else None)
                vid    = getattr(s, "videoId", None) or (s.get("videoId") if isinstance(s, dict) else None)
                log.info("YouTube (search '%s'): %s - %s", query[:40], title, artist)
                return title, artist, cover, vid
        except Exception as e:
            log.warning("Search failed: %s", e)

        return None, None, None, None

    # ── extract video ID ───────────────────────────────────────

    @staticmethod
    def _extract_video_id(file_path: str, existing_id: Optional[str]) -> Optional[str]:
        if existing_id and len(existing_id) == 11:
            return existing_id
        base = os.path.splitext(os.path.basename(file_path))[0]
        m = re.search(r'[(\[]([\w-]{11})[)\]]', base)
        if m:
            return m.group(1)
        m = re.search(r'([\w-]{11})$', base.strip())
        if m:
            return m.group(1)
        return None

    # ── title cleanup ──────────────────────────────────────────

    @staticmethod
    def _clean_title(title: str) -> str:
        if not title:
            return title
        for pat in [
            r'\s*\[.*?\]', r'\s*\(.*?\)', r'\s*【.*?】',
            r'\s*[|•].*', r'\s*ft\.\s.*', r'\s*feat\.\s.*',
            r'\s*-\s*Official.*', r'\s*-\s*Lyrics.*',
            r'\s*-\s*Audio.*', r'\s*-\s*Video.*',
            r'\s*HD$', r'\s*HQ$', r'\s*4K$',
        ]:
            title = re.sub(pat, '', title, flags=re.IGNORECASE)
        return title.strip()

    @staticmethod
    def _title_artist_from_filename(file_path: str):
        base = os.path.splitext(os.path.basename(file_path))[0]
        base = re.sub(r'[(\[][\w-]{11}[)\]]', '', base).strip()
        if " - " in base:
            artist, title = base.split(" - ", 1)
            return title.strip(), artist.strip()
        return base, "Unknown Artist"

    # ── MP3 ────────────────────────────────────────────────────

    async def _fix_mp3(self, file_path, fetch_covers, overwrite, playlist_json_data=None):
        try:
            try:
                id3 = ID3(file_path)
            except ID3NoHeaderError:
                id3 = ID3()
            except Exception:
                id3 = ID3()

            ex_title  = id3.get("TIT2")
            ex_artist = id3.get("TPE1")
            ex_vid_fr = id3.get("TCON")
            ex_vid_id = ex_vid_fr.text[0] if ex_vid_fr and ex_vid_fr.text else None

            ex_cover  = None
            ex_cmime  = None
            for apic in id3.getall("APIC"):
                if getattr(apic, "data", None):
                    ex_cover = apic.data
                    ex_cmime = getattr(apic, "mime", "image/jpeg")
                    break

            video_id = self._extract_video_id(file_path, ex_vid_id)

            fn_title, fn_artist = self._title_artist_from_filename(file_path)
            search_q = f"{fn_artist} - {fn_title}" if fn_artist != "Unknown Artist" else fn_title

            # Check if we have metadata from playlist.json
            json_title = None
            json_artist = None
            json_video_id = None
            if playlist_json_data:
                json_title = playlist_json_data.get("title")
                json_artist = playlist_json_data.get("artist")
                json_video_id = playlist_json_data.get("videoId")
                # Use videoId from JSON if not found in audio file
                if json_video_id and not video_id:
                    video_id = json_video_id

            yt_title, yt_artist, thumb_url, found_vid = await self._fetch_youtube(
                video_id, search_query=search_q)

            if found_vid and not video_id:
                video_id = found_vid

            # Priority: JSON data > YouTube > existing > filename
            title = json_title or yt_title
            artist = json_artist or yt_artist

            if not overwrite:
                if ex_title and ex_title.text and not title:
                    title = ex_title.text[0]
                if ex_artist and ex_artist.text and not artist:
                    artist = ex_artist.text[0]

            if not title or not artist:
                title  = title  or fn_title
                artist = artist or fn_artist

            title = self._clean_title(title)

            if title:
                id3.delall("TIT2"); id3.add(TIT2(encoding=3, text=title))
            if artist:
                id3.delall("TPE1"); id3.add(TPE1(encoding=3, text=artist))
            if video_id:
                id3.delall("TCON"); id3.add(TCON(encoding=3, text=video_id))

            # Save tags first
            id3.save(file_path, v2_version=3, v1=2)

            # Use embed_image_mp3 from add_cover.py for cover embedding
            if fetch_covers and thumb_url and (overwrite or not ex_cover):
                try:
                    from app.logic.metadata.add_cover import embed_image_mp3
                    success = embed_image_mp3(file_path, image_url=thumb_url)
                    if success:
                        log.debug("Cover embedded via add_cover.py")
                except Exception as e:
                    log.warning("Cover embedding failed: %s", e)

            log.info("OK %s", os.path.basename(file_path))
            return True
        except Exception as e:
            log.exception("MP3 error: %s", e)
            return False

    # ── MP3 from JSON ─────────────────────────────────────────

    async def _fix_mp3_from_json(self, file_path, json_metadata, fetch_covers, overwrite):
        """Fix MP3 using only playlist.json data (no YouTube API)"""
        try:
            try:
                id3 = ID3(file_path)
            except ID3NoHeaderError:
                id3 = ID3()
            except Exception:
                id3 = ID3()

            title = json_metadata.get("title")
            artist = json_metadata.get("artist")
            video_id = json_metadata.get("videoId")

            if title:
                id3.delall("TIT2"); id3.add(TIT2(encoding=3, text=title))
            if artist:
                id3.delall("TPE1"); id3.add(TPE1(encoding=3, text=artist))
            if video_id:
                id3.delall("TCON"); id3.add(TCON(encoding=3, text=video_id))

            # Save tags first
            id3.save(file_path, v2_version=3, v1=2)

            # Embed cover from JSON if available
            if fetch_covers and json_metadata.get("cover"):
                try:
                    import base64
                    from app.logic.metadata.add_metadata import _compress_cover
                    from app.logic.metadata.add_cover import embed_image_mp3
                    
                    # Cover is already base64 WebP in JSON, but embed_image_mp3 needs URL or bytes
                    # For now, we'll use the thumbnail URL from JSON if available
                    thumb_url = json_metadata.get("thumbnail_url")
                    if thumb_url:
                        success = embed_image_mp3(file_path, image_url=thumb_url)
                        if success:
                            log.debug("Cover embedded from JSON thumbnail URL")
                except Exception as e:
                    log.warning("JSON cover embedding failed: %s", e)

            log.info("OK (from JSON) %s", os.path.basename(file_path))
            return True
        except Exception as e:
            log.exception("MP3 from JSON error: %s", e)
            return False

    # ── MP4 from JSON ─────────────────────────────────────────

    async def _fix_mp4_from_json(self, file_path, json_metadata, fetch_covers, overwrite):
        """Fix MP4 using only playlist.json data (no YouTube API)"""
        try:
            audio = MP4(file_path)

            title = json_metadata.get("title")
            artist = json_metadata.get("artist")
            video_id = json_metadata.get("videoId")

            if title:
                audio["\xa9nam"] = [title]
            if artist:
                audio["\xa9ART"] = [artist]
            if video_id:
                audio["\xa9cmt"] = [video_id]

            # Save tags first
            audio.save()

            # Embed cover from JSON if available
            if fetch_covers and json_metadata.get("cover"):
                try:
                    from app.logic.metadata.add_cover import embed_image_mp4
                    
                    # Use thumbnail URL from JSON if available
                    thumb_url = json_metadata.get("thumbnail_url")
                    if thumb_url:
                        success = embed_image_mp4(file_path, image_url=thumb_url)
                        if success:
                            log.debug("Cover embedded from JSON thumbnail URL")
                except Exception as e:
                    log.warning("JSON cover embedding failed: %s", e)

            log.info("OK (from JSON) %s", os.path.basename(file_path))
            return True
        except Exception as e:
            log.exception("MP4 from JSON error: %s", e)
            return False

    async def _fix_mp4(self, file_path, fetch_covers, overwrite, playlist_json_data=None):
        try:
            audio = MP4(file_path)

            ex_title  = audio.get("\xa9nam", [None])[0] if "\xa9nam" in audio else None
            ex_artist = audio.get("\xa9ART", [None])[0] if "\xa9ART" in audio else None
            ex_vid_id = audio.get("\xa9cmt", [None])[0] if "\xa9cmt" in audio else None

            ex_cover = None
            if "covr" in audio and audio["covr"]:
                ex_cover = bytes(audio["covr"][0])

            video_id = self._extract_video_id(file_path, ex_vid_id)

            fn_title, fn_artist = self._title_artist_from_filename(file_path)
            search_q = f"{fn_artist} - {fn_title}" if fn_artist != "Unknown Artist" else fn_title

            # Check if we have metadata from playlist.json
            json_title = None
            json_artist = None
            json_video_id = None
            if playlist_json_data:
                json_title = playlist_json_data.get("title")
                json_artist = playlist_json_data.get("artist")
                json_video_id = playlist_json_data.get("videoId")
                # Use videoId from JSON if not found in audio file
                if json_video_id and not video_id:
                    video_id = json_video_id

            yt_title, yt_artist, thumb_url, found_vid = await self._fetch_youtube(
                video_id, search_query=search_q)

            if found_vid and not video_id:
                video_id = found_vid

            # Priority: JSON data > YouTube > existing > filename
            title = json_title or yt_title
            artist = json_artist or yt_artist

            if not overwrite:
                if ex_title and not title:
                    title = ex_title
                if ex_artist and not artist:
                    artist = ex_artist

            if not title or not artist:
                title  = title  or fn_title
                artist = artist or fn_artist

            title = self._clean_title(title)

            if title:
                audio["\xa9nam"] = [title]
            if artist:
                audio["\xa9ART"] = [artist]
            if video_id:
                audio["\xa9cmt"] = [video_id]

            # Save tags first
            audio.save()

            # Use embed_image_mp4 from add_cover.py for cover embedding
            if fetch_covers and thumb_url and (overwrite or not ex_cover):
                try:
                    from app.logic.metadata.add_cover import embed_image_mp4
                    success = embed_image_mp4(file_path, image_url=thumb_url)
                    if success:
                        log.debug("Cover embedded via add_cover.py")
                except Exception as e:
                    log.warning("MP4 cover embedding failed: %s", e)

            log.info("OK %s", os.path.basename(file_path))
            return True
        except Exception as e:
            log.exception("MP4 error: %s", e)
            return False
