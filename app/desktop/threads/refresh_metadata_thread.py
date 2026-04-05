"""
RefreshMetadataThread — replaces broken files by re-downloading from YouTube
instead of trying to fix tags in-place.

Workflow:
  1. Scan files for metadata issues
  2. Delete broken files
  3. Re-download using DownloadThread
  4. Update playlist.json
"""
import logging
import os
from typing import List, Dict, Optional

from PyQt5.QtCore import QThread, pyqtSignal

log = logging.getLogger(__name__)


class RefreshMetadataThread(QThread):
    """Scans, deletes, and re-downloads songs with broken metadata."""

    # Signals for UI progress
    progress = pyqtSignal(int, int, str)  # current, total, filename/status
    complete = pyqtSignal(dict)           # {refreshed: int, failed: int, skipped: int, details: list}
    error = pyqtSignal(str)

    def __init__(self, songs_data: List[Dict], download_path: str,
                 playlist_folder: Optional[str] = None):
        super().__init__()
        self.songs_data = songs_data
        self.download_path = download_path
        self.playlist_folder = playlist_folder
        self._stop = False

    def stop(self):
        self._stop = True

    def _search_youtube_for_song(self, title: str, artist: str, file_path: str) -> Optional[str]:
        """
        Search YouTube for a song by title + artist and return the videoId.
        Uses the same search logic as FixMetadataThread.
        """
        import asyncio
        import re
        
        try:
            # Clean title for better search
            search_title = title
            for pat in [
                r'\s*\[.*?\]', r'\s*\(.*?\)', r'\s*【.*?】',
                r'\s*[|•].*', r'\s*ft\.\s.*', r'\s*feat\.\s.*',
                r'\s*-\s*Official.*', r'\s*-\s*Lyrics.*',
                r'\s*-\s*Audio.*', r'\s*-\s*Video.*',
                r'\s*HD$', r'\s*HQ$', r'\s*4K$',
            ]:
                search_title = re.sub(pat, '', search_title, flags=re.IGNORECASE)
            search_title = search_title.strip()
            
            # Build search query
            if artist and artist != "Unknown Artist":
                search_query = f"{artist} - {search_title}"
            else:
                search_query = search_title
            
            log.info("Searching YouTube for: %s", search_query)
            
            # Use async function to search YouTube
            async def search():
                try:
                    from app.logic.api_handler.handle_yt import get_song_by_string
                    data = await get_song_by_string(search_query)
                    songs = data.get("songs", [])
                    if songs:
                        s = songs[0]
                        vid = getattr(s, "videoId", None) or (s.get("videoId") if isinstance(s, dict) else None)
                        return vid
                except Exception as e:
                    log.warning("YouTube search failed: %s", e)
                return None
            
            # Run async search
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            if loop.is_running():
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    video_id = new_loop.run_until_complete(search())
                finally:
                    new_loop.close()
                    asyncio.set_event_loop(loop)
            else:
                video_id = loop.run_until_complete(search())
            
            if video_id:
                log.info("✅ Found video ID '%s' for: %s", video_id, os.path.basename(file_path))
                return video_id
            else:
                log.warning("❌ No results for: %s", search_query)
                return None
                
        except Exception as e:
            log.error("Search error: %s", e)
            return None

    def run(self):
        results = {
            "refreshed": 0,
            "failed": 0,
            "skipped": 0,
            "details": []
        }

        total = len(self.songs_data)
        log.info("Starting metadata refresh for %d songs", total)

        for idx, song_data in enumerate(self.songs_data):
            if self._stop:
                log.info("Refresh stopped by user")
                break

            file_path = song_data.get("file_path") or song_data.get("path", "")
            metadata = song_data.get("metadata", {})
            video_id = metadata.get("videoId", "")
            
            # Extract title and artist for search
            title = metadata.get("title", "")
            artist = metadata.get("artist", "")

            if not video_id:
                # Try to extract from filename
                import re
                base = os.path.splitext(os.path.basename(file_path))[0]
                m = re.search(r'[(\[]([\w-]{11})[)\]]', base)
                if m:
                    video_id = m.group(1)
                else:
                    m = re.search(r'([\w-]{11})$', base.strip())
                    if m:
                        video_id = m.group(1)

            # If still no video_id, try to search YouTube by title+artist
            if not video_id:
                self.progress.emit(idx + 1, total, f"🔍 Searching: {os.path.basename(file_path)}")
                try:
                    video_id = self._search_youtube_for_song(title, artist, file_path)
                    if video_id:
                        log.info("Found video ID for %s: %s", os.path.basename(file_path), video_id)
                    else:
                        log.warning("No video ID found for %s even after search", file_path)
                except Exception as e:
                    log.error("Search failed for %s: %s", file_path, e)

            if not video_id:
                log.warning("No video ID for %s, skipping", file_path)
                results["skipped"] += 1
                results["details"].append({
                    "file": os.path.basename(file_path),
                    "status": "Skipped",
                    "reason": "No video ID found (search failed)"
                })
                self.progress.emit(idx + 1, total, f"⚠️ No video ID: {os.path.basename(file_path)}")
                continue

            # Step 1: Delete old file
            self.progress.emit(idx + 1, total, f"🗑️ Deleting: {os.path.basename(file_path)}")
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    log.info("Deleted: %s", file_path)
                else:
                    log.warning("File not found: %s", file_path)
            except Exception as e:
                log.error("Failed to delete %s: %s", file_path, e)
                results["failed"] += 1
                results["details"].append({
                    "file": os.path.basename(file_path),
                    "status": "Failed",
                    "reason": f"Delete error: {e}"
                })
                continue

            # Step 2: Re-download
            self.progress.emit(idx + 1, total, f"⬇️ Downloading: {os.path.basename(file_path)}")
            try:
                from app.logic.ultimate_downloader import download_song
                from app.desktop.utils.helpers import clean_filename

                # Extract title and artist for download
                title = metadata.get("title", os.path.splitext(os.path.basename(file_path))[0])
                artist = metadata.get("artist", "Unknown Artist")

                safe_title = clean_filename(title)
                safe_artist = clean_filename(artist)

                new_path = download_song(
                    video_id,
                    safe_title,
                    format_ext="mp3",
                    base_path=self.download_path,
                )

                if new_path and os.path.exists(new_path):
                    # Rename to standard format
                    target_name = f"{safe_artist} - {safe_title}.mp3"
                    target_path = os.path.join(os.path.dirname(new_path), target_name)

                    if os.path.basename(new_path) != target_name:
                        try:
                            if os.path.exists(target_path):
                                os.remove(target_path)
                            os.rename(new_path, target_path)
                            new_path = target_path
                        except Exception as e:
                            log.error("Rename failed: %s", e)

                    log.info("Re-downloaded: %s", new_path)
                    results["refreshed"] += 1
                    results["details"].append({
                        "file": os.path.basename(new_path),
                        "status": "Refreshed",
                        "new_path": new_path
                    })
                    self.progress.emit(idx + 1, total, f"✅ Refreshed: {os.path.basename(new_path)}")

                    # Update playlist.json with new path
                    self._update_playlist_json(file_path, new_path)
                else:
                    log.error("Download failed for video %s", video_id)
                    results["failed"] += 1
                    results["details"].append({
                        "file": os.path.basename(file_path),
                        "status": "Failed",
                        "reason": "Download failed"
                    })
            except Exception as e:
                log.exception("Re-download error for %s: %s", video_id, e)
                results["failed"] += 1
                results["details"].append({
                    "file": os.path.basename(file_path),
                    "status": "Failed",
                    "reason": str(e)
                })

        log.info("Refresh complete: %d refreshed, %d failed, %d skipped",
                 results["refreshed"], results["failed"], results["skipped"])
        self.complete.emit(results)

    def _update_playlist_json(self, old_path: str, new_path: str):
        """Update playlist.json to reflect the new file path."""
        if not self.playlist_folder or not os.path.isdir(self.playlist_folder):
            return

        try:
            from app.desktop.utils.playlist_manager import PlaylistManager
            import json

            playlist_data = PlaylistManager.get_playlist_info(self.playlist_folder)
            updated = False

            for song in playlist_data.get("songs", []):
                song_path = song.get("file_path") or song.get("path", "")
                if os.path.normcase(os.path.abspath(song_path)) == os.path.normcase(os.path.abspath(old_path)):
                    # Update path
                    song["path"] = new_path
                    song["file_path"] = new_path

                    # Re-extract metadata
                    from app.logic.metadata.add_metadata import verify_metadata
                    ext = os.path.splitext(new_path)[1].lstrip(".").lower()
                    metadata = verify_metadata(new_path, ext)

                    if metadata:
                        song["title"] = metadata.get("title", song.get("title"))
                        song["artist"] = metadata.get("artist", song.get("artist"))
                        song["videoId"] = metadata.get("videoId", song.get("videoId", ""))
                        song["cover"] = metadata.get("cover", "")
                        song["has_cover"] = metadata.get("has_cover", False)

                    updated = True
                    log.info("Updated playlist.json for: %s", os.path.basename(new_path))
                    break

            if updated:
                playlist_data["modified"] = os.path.getctime(self.playlist_folder)
                json_path = os.path.join(self.playlist_folder, "playlist.json")
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(playlist_data, f, indent=2, ensure_ascii=False)

        except Exception as e:
            log.error("Error updating playlist.json: %s", e)
