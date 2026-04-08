# playlist_manager.py
"""
Playlist manager for JSON-based playlist storage
"""

import json
import logging
import os
from typing import List, Dict, Any, Optional
import shutil
from PyQt5.QtWidgets import QMessageBox
from app.desktop.utils.metadata import get_audio_metadata

log = logging.getLogger(__name__)


# Master playlist: every download is added here; shown first in the UI.
DEFAULT_PLAYLIST_NAME = "All Songs"
LEGACY_AUTO_PLAYLIST_FOLDER = "All playlist Automaticly"


class PlaylistManager:
    """Manages playlist operations with JSON storage"""

    @staticmethod
    def default_playlist_folder_path(base_path: str) -> str:
        """Absolute path to the default «All Songs» playlist folder."""
        return os.path.join(os.path.abspath(base_path), DEFAULT_PLAYLIST_NAME)

    @staticmethod
    def ensure_default_playlist(base_path: str) -> str:
        """
        Ensure the master «All Songs» playlist exists (valid playlist.json).
        Renames legacy folder «All playlist Automaticly» → «All Songs» if needed.
        Returns the folder path.
        """
        base_path = os.path.abspath(base_path or "")
        if not base_path:
            return ""

        legacy = os.path.join(base_path, LEGACY_AUTO_PLAYLIST_FOLDER)
        target = os.path.join(base_path, DEFAULT_PLAYLIST_NAME)

        if os.path.isdir(legacy) and not os.path.isdir(target):
            try:
                os.rename(legacy, target)
            except OSError as e:
                log.warning("Could not rename legacy playlist folder: %s", e)

        os.makedirs(target, exist_ok=True)
        json_path = os.path.join(target, "playlist.json")
        if not os.path.isfile(json_path):
            PlaylistManager.create_playlist(target, DEFAULT_PLAYLIST_NAME)
        return target

    @staticmethod
    def is_default_playlist_folder(folder_path: str, base_path: str) -> bool:
        """True if this folder is the master «All Songs» playlist."""
        try:
            return os.path.normcase(os.path.abspath(folder_path)) == os.path.normcase(
                PlaylistManager.default_playlist_folder_path(base_path)
            )
        except OSError:
            return False

    @staticmethod
    def sort_playlists_default_first(playlists: List[Dict[str, Any]], base_path: str) -> List[Dict[str, Any]]:
        """Put «All Songs» first; other playlists sorted by name."""
        def key(pl: Dict[str, Any]) -> tuple:
            fp = pl.get("folder_path") or ""
            name = (pl.get("name") or pl.get("folder_name") or "").strip().lower()
            is_def = (
                name == DEFAULT_PLAYLIST_NAME.lower()
                or PlaylistManager.is_default_playlist_folder(fp, base_path)
            )
            return (0 if is_def else 1, name)

        return sorted(playlists, key=key)

    @staticmethod
    def create_playlist(folder_path: str, name: str) -> bool:
        """Create a new playlist with JSON metadata"""
        try:
            os.makedirs(folder_path, exist_ok=True)
            
            playlist_data = {
                "name": name,
                "version": "1.0",
                "created": os.path.getctime(folder_path),
                "modified": os.path.getctime(folder_path),
                "songs": [],
                "metadata": {
                    "cover_color": "#FF6B6B",
                    "description": "",
                    "tags": []
                }
            }
            
            json_path = os.path.join(folder_path, "playlist.json")
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(playlist_data, f, indent=2, ensure_ascii=False)
            
            return True
        except Exception as e:
            log.error("Error creating playlist: %s", e)
            return False
    
    @staticmethod
    def get_playlist_info(folder_path: str) -> Dict[str, Any]:
        """Get playlist information from JSON"""
        json_path = os.path.join(folder_path, "playlist.json")
        
        if not os.path.exists(json_path):
            # Create default playlist data
            return {
                "name": os.path.basename(folder_path),
                "version": "1.0",
                "created": os.path.getctime(folder_path) if os.path.exists(folder_path) else 0,
                "modified": os.path.getctime(folder_path) if os.path.exists(folder_path) else 0,
                "songs": [],
                "metadata": {
                    "cover_color": "#FF6B6B",
                    "description": "",
                    "tags": []
                }
            }
        
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Ensure all required fields exist
            if "songs" not in data:
                data["songs"] = []
            if "metadata" not in data:
                data["metadata"] = {
                    "cover_color": "#FF6B6B",
                    "description": "",
                    "tags": []
                }
            
            return data
        except Exception as e:
            log.error("Error reading playlist JSON: %s", e)
            return {
                "name": os.path.basename(folder_path),
                "version": "1.0",
                "created": 0,
                "modified": 0,
                "songs": [],
                "metadata": {
                    "cover_color": "#FF6B6B",
                    "description": "",
                    "tags": []
                }
            }
    
    @staticmethod
    def _norm_file_path(p: str) -> str:
        try:
            return os.path.normcase(os.path.abspath(p))
        except OSError:
            return p

    @staticmethod
    def add_song_to_playlist(
        folder_path: str,
        file_path: str,
        metadata: Optional[Dict] = None,
        *,
        dedupe_paths_only: bool = False,
    ) -> bool:
        """
        Add a song reference to playlist JSON.

        dedupe_paths_only=True — tylko ten sam plik (znormalizowana ścieżka) jest uznawany za duplikat;
        ignoruje duplikat po tytule+wykonawcy (np. dwa różne MP3 z tym samym tagiem).
        """
        try:
            playlist_data = PlaylistManager.get_playlist_info(folder_path)

            # Get or create metadata
            if metadata is None:
                if os.path.exists(file_path):
                    metadata = get_audio_metadata(file_path)
                else:
                    metadata = {
                        "title": os.path.splitext(os.path.basename(file_path))[0],
                        "artist": "Unknown Artist",
                        "duration": 0,
                        "videoId": "",
                    }

            name = os.path.splitext(os.path.basename(file_path))[0]
            playable_uri = os.path.abspath(file_path)

            # Get cover data from song metadata (both URL and base64 fallback)
            cover_data = {"cover_base64": "", "cover_url": "", "has_cover": False}
            if os.path.exists(file_path) and metadata.get("has_cover"):
                from app.logic.metadata.add_metadata import extract_cover_from_metadata
                ext = os.path.splitext(file_path)[1].lstrip(".").lower()
                video_id = metadata.get("videoId", "")
                cover_data = extract_cover_from_metadata(file_path, ext, video_id)

            song_entry = {
                "videoId": metadata.get("videoId", ""),
                "title": metadata.get("title", name),
                "artist": metadata.get("artist", "Unknown Artist"),
                "duration": metadata.get("duration", 0),
                "cover": cover_data.get("cover_url", ""),  # Primary: YouTube URL
                "cover_base64": cover_data.get("cover_base64", ""),  # Fallback: offline mode
                "path": playable_uri,
                "viewed": False,
            }
            
            # Check if song already exists
            new_key = PlaylistManager._norm_file_path(file_path)
            new_video_id = metadata.get("videoId", "").strip()
            
            for existing_song in playlist_data["songs"]:
                # Check by file path (normalized)
                ep = existing_song.get("file_path") or existing_song.get("path", "")
                if ep and PlaylistManager._norm_file_path(ep) == new_key:
                    return False
                
                # Check by videoId (if both have it and match)
                if new_video_id:
                    existing_vid = existing_song.get("videoId", "").strip()
                    if existing_vid and existing_vid == new_video_id:
                        return False

            # Add song
            playlist_data["songs"].append(song_entry)
            playlist_data["modified"] = os.path.getctime(folder_path)
            
            # Save updated playlist
            json_path = os.path.join(folder_path, "playlist.json")
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(playlist_data, f, indent=2, ensure_ascii=False)
            
            return True
        except Exception as e:
            log.error("Error adding song to playlist: %s", e)
            return False
    
    @staticmethod
    def remove_song_from_playlist(folder_path: str, song_index: int) -> bool:
        """Remove a song from playlist JSON"""
        try:
            playlist_data = PlaylistManager.get_playlist_info(folder_path)
            
            if 0 <= song_index < len(playlist_data["songs"]):
                playlist_data["songs"].pop(song_index)
                playlist_data["modified"] = os.path.getctime(folder_path)
                
                json_path = os.path.join(folder_path, "playlist.json")
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(playlist_data, f, indent=2, ensure_ascii=False)
                
                return True
            return False
        except Exception as e:
            log.error("Error removing song from playlist: %s", e)
            return False

    @staticmethod
    def remove_song_by_file_path(folder_path: str, file_path: str) -> bool:
        """Remove the entry whose file_path matches (normalized compare)."""
        try:
            def _norm(p: str) -> str:
                try:
                    return os.path.normcase(os.path.normpath(p))
                except OSError:
                    return os.path.normcase(p or "")

            target = _norm(file_path)
            if not target:
                return False
            playlist_data = PlaylistManager.get_playlist_info(folder_path)
            songs = playlist_data.get("songs", [])
            for i, s in enumerate(songs):
                fp = s.get("file_path", "")
                if fp and _norm(fp) == target:
                    songs.pop(i)
                    playlist_data["modified"] = os.path.getctime(folder_path)
                    json_path = os.path.join(folder_path, "playlist.json")
                    with open(json_path, 'w', encoding='utf-8') as f:
                        json.dump(playlist_data, f, indent=2, ensure_ascii=False)
                    return True
            return False
        except Exception as e:
            log.error("Error removing song by path: %s", e)
            return False
    
    @staticmethod
    def update_song_metadata(folder_path: str, song_index: int, metadata: Dict[str, Any]) -> bool:
        """Update metadata for a song in playlist"""
        try:
            playlist_data = PlaylistManager.get_playlist_info(folder_path)
            
            if 0 <= song_index < len(playlist_data["songs"]):
                song = playlist_data["songs"][song_index]
                
                # Update metadata
                for key, value in metadata.items():
                    if key in [
                        "title", "artist", "album", "duration",
                        "videoId", "cover", "path", "viewed",
                        "has_cover", "cover_mime", "cover_size", "needs_fix",
                    ]:
                        song[key] = value
                
                playlist_data["modified"] = os.path.getctime(folder_path)
                
                json_path = os.path.join(folder_path, "playlist.json")
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(playlist_data, f, indent=2, ensure_ascii=False)
                
                return True
            return False
        except Exception as e:
            log.error("Error updating song metadata: %s", e)
            return False
    
    @staticmethod
    def iter_playlist_folder_paths(base_path: str) -> List[str]:
        """
        Katalogi playlist pod base_path:
        - bezpośrednie podfoldery (np. «All Songs», «Moja lista»),
        - jeśli istnieje folder ``playlists`` bez ``playlist.json``, traktuj go jako
          kontener i dodaj jego **podfoldery** (np. ``.../songs/playlists/Rock``).
        """
        base_path = os.path.abspath(base_path)
        if not os.path.isdir(base_path):
            return []
        out: List[str] = []
        try:
            names = sorted(os.listdir(base_path), key=str.lower)
        except OSError:
            return []
        for item in names:
            item_path = os.path.join(base_path, item)
            if not os.path.isdir(item_path):
                continue
            jp = os.path.join(item_path, "playlist.json")
            if item.lower() == "playlists" and not os.path.isfile(jp):
                try:
                    for sub in sorted(os.listdir(item_path), key=str.lower):
                        sub_path = os.path.join(item_path, sub)
                        if os.path.isdir(sub_path):
                            out.append(sub_path)
                except OSError as e:
                    log.debug("iter_playlist_folder_paths playlists/: %s", e)
                continue
            out.append(item_path)
        return out

    @staticmethod
    def get_all_playlists(base_path: str) -> List[Dict[str, Any]]:
        """Get all playlists from base directory"""
        playlists = []

        if not os.path.exists(base_path):
            return playlists

        for item_path in PlaylistManager.iter_playlist_folder_paths(base_path):
            playlist_data = PlaylistManager.get_playlist_info(item_path)
            playlist_data["folder_path"] = item_path
            playlist_data["folder_name"] = os.path.basename(item_path)
            playlists.append(playlist_data)

        return playlists
    
    @staticmethod
    def search_in_playlists(base_path: str, query: str) -> Dict[str, List[Dict[str, Any]]]:
        """Search for songs and playlists matching query"""
        results = {
            "songs": [],
            "playlists": []
        }
        
        query = query.lower()
        
        # Search in all playlists
        playlists = PlaylistManager.get_all_playlists(base_path)
        
        for playlist in playlists:
            playlist_name = playlist["name"].lower()
            
            # Check playlist name
            if query in playlist_name:
                results["playlists"].append({
                    "type": "playlist",
                    "name": playlist["name"],
                    "folder_path": playlist["folder_path"],
                    "song_count": len(playlist["songs"]),
                    "match_reason": "Playlist name matches"
                })
            
            # Search songs in this playlist
            for song in playlist["songs"]:
                title = song.get("title", "").lower()
                artist = song.get("artist", "").lower()
                album = song.get("album", "").lower()
                
                if (query in title or query in artist or query in album):
                    results["songs"].append({
                        "type": "song",
                        "title": song.get("title"),
                        "artist": song.get("artist"),
                        "album": song.get("album"),
                        "file_path": song.get("file_path") or song.get("path", ""),
                        "playlist": playlist["name"],
                        "playlist_path": playlist["folder_path"],
                        "match_reason": "Song metadata matches"
                    })
        
        return results
    
    @staticmethod
    def generate_recommendations(base_path: str, current_playlist: Optional[str] = None) -> List[Dict[str, Any]]:
        """Generate playlist recommendations"""
        playlists = PlaylistManager.get_all_playlists(base_path)
        
        if not playlists:
            return []
        
        # Simple recommendation logic
        recommendations = []
        
        # Get playlists with most songs
        playlists_by_size = sorted(playlists, key=lambda x: len(x["songs"]), reverse=True)[:3]
        
        for playlist in playlists_by_size:
            if playlist["folder_path"] != current_playlist:
                recommendations.append({
                    "type": "recommendation",
                    "reason": "Popular playlist",
                    "playlist": playlist,
                    "score": len(playlist["songs"]) / 10.0
                })
        
        # Get recently modified playlists
        playlists_by_date = sorted(playlists, key=lambda x: x.get("modified", 0), reverse=True)[:2]
        
        for playlist in playlists_by_date:
            if playlist["folder_path"] != current_playlist:
                recommendations.append({
                    "type": "recommendation",
                    "reason": "Recently updated",
                    "playlist": playlist,
                    "score": 0.8
                })
        
        return recommendations
    
    @staticmethod
    def fix_playlist_metadata(folder_path: str) -> Dict[str, Any]:
        """Fix metadata for all songs in playlist"""
        results = {
            "fixed": 0,
            "errors": 0,
            "details": []
        }
        
        playlist_data = PlaylistManager.get_playlist_info(folder_path)
        
        for i, song in enumerate(playlist_data["songs"]):
            file_path = song.get("file_path") or song.get("path", "")

            if file_path and os.path.exists(file_path):
                try:
                    metadata = get_audio_metadata(file_path)

                    # Update song metadata
                    song["title"] = metadata.get("title", song.get("title"))
                    song["artist"] = metadata.get("artist", song.get("artist"))
                    song["album"] = metadata.get("album", song.get("album"))
                    song["duration"] = metadata.get("duration", song.get("duration"))
                    song["videoId"] = metadata.get("videoId", song.get("videoId", ""))

                    # Update cover data (both URL and base64 fallback)
                    from app.logic.metadata.add_metadata import extract_cover_from_metadata
                    ext = os.path.splitext(file_path)[1].lstrip(".").lower()
                    video_id = song.get("videoId", "")
                    cover_data = extract_cover_from_metadata(file_path, ext, video_id)
                    song["cover"] = cover_data.get("cover_url", "")  # Primary: YouTube URL
                    song["cover_base64"] = cover_data.get("cover_base64", "")  # Fallback
                    
                    results["fixed"] += 1
                    results["details"].append({
                        "song": song["title"],
                        "status": "Fixed",
                        "details": f"Updated metadata from file"
                    })
                except Exception as e:
                    results["errors"] += 1
                    results["details"].append({
                        "song": song.get("title", "Unknown"),
                        "status": "Error",
                        "details": str(e)
                    })
        
        # Save updated playlist
        if results["fixed"] > 0:
            playlist_data["modified"] = os.path.getctime(folder_path)
            json_path = os.path.join(folder_path, "playlist.json")
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(playlist_data, f, indent=2, ensure_ascii=False)
        
        return results
    
    @staticmethod
    def export_playlist(folder_path: str, export_path: str) -> bool:
        """Export playlist to a JSON file"""
        try:
            playlist_data = PlaylistManager.get_playlist_info(folder_path)
            
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(playlist_data, f, indent=2, ensure_ascii=False)
            
            return True
        except Exception as e:
            log.error("Error exporting playlist: %s", e)
            return False
    
    @staticmethod
    def import_playlist(import_path: str, target_folder: str) -> bool:
        """Import playlist from JSON file"""
        try:
            with open(import_path, 'r', encoding='utf-8') as f:
                playlist_data = json.load(f)

            # Create playlist folder
            os.makedirs(target_folder, exist_ok=True)

            # Save to new location
            json_path = os.path.join(target_folder, "playlist.json")
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(playlist_data, f, indent=2, ensure_ascii=False)

            return True
        except Exception as e:
            log.error("Error importing playlist: %s", e)
            return False

    @staticmethod
    def recompress_all_covers(folder_path: str) -> Dict[str, Any]:
        """
        Recompress all cover images in playlist to reduce JSON size.
        Now stores YouTube URL as primary and base64 as fallback.
        Returns stats: {"updated": int, "errors": int, "details": list}
        """
        from app.logic.metadata.add_metadata import extract_cover_from_metadata

        results = {
            "updated": 0,
            "errors": 0,
            "details": []
        }

        playlist_data = PlaylistManager.get_playlist_info(folder_path)

        for i, song in enumerate(playlist_data["songs"]):
            file_path = song.get("file_path") or song.get("path", "")

            if file_path and os.path.exists(file_path):
                try:
                    ext = os.path.splitext(file_path)[1].lstrip(".").lower()
                    video_id = song.get("videoId", "")
                    cover_data = extract_cover_from_metadata(file_path, ext, video_id)

                    if cover_data.get("has_cover"):
                        song["cover"] = cover_data.get("cover_url", "")  # Primary: YouTube URL
                        song["cover_base64"] = cover_data.get("cover_base64", "")  # Fallback
                        results["updated"] += 1
                        results["details"].append({
                            "song": song.get("title", "Unknown"),
                            "status": "Compressed",
                            "details": f"Cover updated with YouTube URL + base64 fallback"
                        })
                    else:
                        results["errors"] += 1
                        results["details"].append({
                            "song": song.get("title", "Unknown"),
                            "status": "No cover",
                            "details": "No embedded cover found in audio file"
                        })
                except Exception as e:
                    results["errors"] += 1
                    results["details"].append({
                        "song": song.get("title", "Unknown"),
                        "status": "Error",
                        "details": str(e)
                    })

        # Save updated playlist
        if results["updated"] > 0:
            playlist_data["modified"] = os.path.getctime(folder_path)
            json_path = os.path.join(folder_path, "playlist.json")
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(playlist_data, f, indent=2, ensure_ascii=False)

        return results