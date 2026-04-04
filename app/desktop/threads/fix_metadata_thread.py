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


class FixMetadataThread(QThread):
    progress = pyqtSignal(int, int, str)   # current, total, filename
    complete = pyqtSignal(list)            # results list
    error    = pyqtSignal(str)

    def __init__(self, songs_data: List[Dict]):
        super().__init__()
        self.songs_data = songs_data
        self._stop = False

    def stop(self):
        self._stop = True

    # ── entry point ────────────────────────────────────────────

    def run(self):
        results = []
        total = len(self.songs_data)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        for idx, song_data in enumerate(self.songs_data):
            if self._stop:
                break

            file_path    = song_data.get("file_path") or song_data.get("path", "")
            fetch_covers = song_data.get("fetch_covers", True)
            overwrite    = song_data.get("overwrite", False)

            self.progress.emit(idx + 1, total, os.path.basename(file_path))

            result = {"file_path": file_path, "success": False, "error": None}

            try:
                ext = os.path.splitext(file_path)[1].lower()
                if ext == ".mp3":
                    ok = loop.run_until_complete(
                        self._fix_mp3(file_path, fetch_covers, overwrite))
                elif ext in (".mp4", ".m4a"):
                    ok = loop.run_until_complete(
                        self._fix_mp4(file_path, fetch_covers, overwrite))
                else:
                    result["error"] = f"Unsupported format: {ext}"
                    results.append(result)
                    continue
                result["success"] = ok
            except Exception as e:
                result["error"] = str(e)
                log.error("Error fixing %s: %s", file_path, e)

            results.append(result)

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

    async def _download_cover(self, url: str) -> tuple:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                resp.raise_for_status()
                data = await resp.read()
                ct = resp.headers.get("content-type", "image/jpeg")
                mime = "image/png" if "png" in ct else "image/jpeg"
                return data, mime

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

    async def _fix_mp3(self, file_path, fetch_covers, overwrite):
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

            yt_title, yt_artist, thumb_url, found_vid = await self._fetch_youtube(
                video_id, search_query=search_q)

            if found_vid and not video_id:
                video_id = found_vid

            title  = yt_title
            artist = yt_artist

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

            cover_data = ex_cover
            cover_mime = ex_cmime

            if fetch_covers and thumb_url and (overwrite or not cover_data):
                try:
                    cover_data, cover_mime = await self._download_cover(thumb_url)
                except Exception as e:
                    log.warning("Cover download failed: %s", e)

            if cover_data and (overwrite or not ex_cover):
                id3.delall("APIC")
                id3.add(APIC(encoding=3, mime=cover_mime or "image/jpeg",
                             type=3, desc="Cover", data=cover_data))
                log.debug("Cover set (%d bytes)", len(cover_data))

            id3.save(file_path, v2_version=3, v1=2)
            log.info("OK %s", os.path.basename(file_path))
            return True
        except Exception as e:
            log.exception("MP3 error: %s", e)
            return False

    # ── MP4 / M4A ──────────────────────────────────────────────

    async def _fix_mp4(self, file_path, fetch_covers, overwrite):
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

            yt_title, yt_artist, thumb_url, found_vid = await self._fetch_youtube(
                video_id, search_query=search_q)

            if found_vid and not video_id:
                video_id = found_vid

            title  = yt_title
            artist = yt_artist

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

            if fetch_covers and thumb_url and (overwrite or not ex_cover):
                try:
                    cover_data, _ = await self._download_cover(thumb_url)
                    fmt = MP4Cover.FORMAT_PNG if thumb_url.lower().endswith(".png") else MP4Cover.FORMAT_JPEG
                    audio["covr"] = [MP4Cover(cover_data, fmt)]
                    log.debug("Cover set for MP4 (%d bytes)", len(cover_data))
                except Exception as e:
                    log.warning("MP4 cover download failed: %s", e)

            audio.save()
            log.info("OK %s", os.path.basename(file_path))
            return True
        except Exception as e:
            log.exception("MP4 error: %s", e)
            return False
