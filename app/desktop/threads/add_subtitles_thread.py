"""
AddSubtitlesThread —批量下载歌词并添加到 playlist.json
"""
import json
import os
import logging
from PyQt5.QtCore import QThread, pyqtSignal

log = logging.getLogger(__name__)


class AddSubtitlesThread(QThread):
    """
    Batch download lyrics (SRT) for songs in playlist.json.
    
    Signals:
        progress(current: int, total: int, title: str)
        complete(success: int, failed: int)
        error(message: str)
    """
    
    progress = pyqtSignal(int, int, str)  # current, total, song_title
    complete = pyqtSignal(int, int)       # success_count, failed_count
    error = pyqtSignal(str)
    
    def __init__(self, playlist_folder: str, lang: str = "en", parent=None):
        super().__init__(parent)
        self.playlist_folder = playlist_folder
        self.lang = lang
        self._stop = False
    
    def stop(self):
        self._stop = True
    
    def run(self):
        try:
            log.info("Lyrics batch job start: folder=%s lang=%s", self.playlist_folder, self.lang)
            playlist_file = os.path.join(self.playlist_folder, "playlist.json")

            if not os.path.isfile(playlist_file):
                log.error("Playlist file not found: %s", playlist_file)
                self.error.emit(f"Playlist file not found: {playlist_file}")
                return

            # Load playlist
            with open(playlist_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            songs = data.get("songs", [])

            # Filter: need videoId, skip if already has lyrics
            to_process = []
            for i, song in enumerate(songs):
                vid = song.get("videoId", "").strip()
                if vid and "lyrics" not in song:
                    to_process.append((i, song))

            total = len(to_process)
            log.info("Lyrics batch scan: total_songs=%d need_lyrics=%d", len(songs), total)
            if total == 0:
                log.info("Lyrics batch job done: no songs to process")
                self.complete.emit(0, 0)
                return
            
            success = 0
            failed = 0
            
            from app.logic.subtitles.subtitles_downloader import get_subtitles_srt
            
            for idx, (song_index, song) in enumerate(to_process):
                if self._stop:
                    break
                
                title = song.get("title", "Unknown")
                video_id = song["videoId"]
                
                self.progress.emit(idx + 1, total, title)
                
                try:
                    srt_content = get_subtitles_srt(video_id, self.lang)
                    songs[song_index]["lyrics"] = srt_content
                    success += 1
                    
                    # Save every 5 songs
                    if success % 5 == 0:
                        self._save_playlist(playlist_file, data)
                        
                except FileNotFoundError:
                    # No subtitles available - skip (don't add field)
                    failed += 1
                    log.debug("No lyrics for %s (%s)", title, video_id)
                except Exception as exc:
                    failed += 1
                    log.warning("Failed to download lyrics for %s: %s", title, exc)
            
            # Final save
            self._save_playlist(playlist_file, data)

            log.info("Lyrics batch job done: success=%d failed=%d", success, failed)
            self.complete.emit(success, failed)
            
        except Exception as exc:
            self.error.emit(str(exc))
    
    def _save_playlist(self, path: str, data: dict):
        """Save playlist to disk."""
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as exc:
            log.error("Failed to save playlist: %s", exc)
            self.error.emit(f"Failed to save playlist: {exc}")
