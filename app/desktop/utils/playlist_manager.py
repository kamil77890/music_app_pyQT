# playlist_manager.py
"""
Playlist manager for JSON-based playlist storage
"""

import json
import os
from typing import List, Dict, Any, Optional
import shutil
from PyQt5.QtWidgets import QMessageBox
from app.desktop.utils.metadata import get_audio_metadata


class PlaylistManager:
    """Manages playlist operations with JSON storage"""
    
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
            print(f"Error creating playlist: {e}")
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
            print(f"Error reading playlist JSON: {e}")
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
    def add_song_to_playlist(folder_path: str, file_path: str, metadata: Optional[Dict] = None) -> bool:
        """Add a song reference to playlist JSON"""
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
                        "album": "Unknown Album",
                        "duration": 0,
                        "has_cover": False,
                        "needs_fix": True
                    }
            
            # Create song entry
            song_entry = {
                "file_path": file_path,
                "title": metadata.get("title", os.path.splitext(os.path.basename(file_path))[0]),
                "artist": metadata.get("artist", "Unknown Artist"),
                "album": metadata.get("album", "Unknown Album"),
                "duration": metadata.get("duration", 0),
                "has_cover": metadata.get("has_cover", False),
                "cover_mime": metadata.get("cover_mime"),
                "cover_size": metadata.get("cover_size", 0),
                "needs_fix": metadata.get("needs_fix", False),
                "added": os.path.getctime(file_path) if os.path.exists(file_path) else 0
            }
            
            # Check if song already exists
            for existing_song in playlist_data["songs"]:
                if (existing_song.get("file_path") == file_path or 
                    (existing_song.get("title") == song_entry["title"] and 
                     existing_song.get("artist") == song_entry["artist"])):
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
            print(f"Error adding song to playlist: {e}")
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
            print(f"Error removing song from playlist: {e}")
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
                    if key in ["title", "artist", "album", "duration", "has_cover", "cover_mime", "cover_size", "needs_fix"]:
                        song[key] = value
                
                playlist_data["modified"] = os.path.getctime(folder_path)
                
                json_path = os.path.join(folder_path, "playlist.json")
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(playlist_data, f, indent=2, ensure_ascii=False)
                
                return True
            return False
        except Exception as e:
            print(f"Error updating song metadata: {e}")
            return False
    
    @staticmethod
    def get_all_playlists(base_path: str) -> List[Dict[str, Any]]:
        """Get all playlists from base directory"""
        playlists = []
        
        if not os.path.exists(base_path):
            return playlists
        
        for item in os.listdir(base_path):
            item_path = os.path.join(base_path, item)
            if os.path.isdir(item_path):
                playlist_data = PlaylistManager.get_playlist_info(item_path)
                playlist_data["folder_path"] = item_path
                playlist_data["folder_name"] = item
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
                        "file_path": song.get("file_path"),
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
            file_path = song.get("file_path")
            
            if file_path and os.path.exists(file_path):
                try:
                    metadata = get_audio_metadata(file_path)
                    
                    # Update song metadata
                    song["title"] = metadata.get("title", song.get("title"))
                    song["artist"] = metadata.get("artist", song.get("artist"))
                    song["album"] = metadata.get("album", song.get("album"))
                    song["duration"] = metadata.get("duration", song.get("duration"))
                    song["has_cover"] = metadata.get("has_cover", song.get("has_cover", False))
                    song["cover_mime"] = metadata.get("cover_mime", song.get("cover_mime"))
                    song["cover_size"] = metadata.get("cover_size", song.get("cover_size", 0))
                    song["needs_fix"] = metadata.get("needs_fix", False)
                    
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
            print(f"Error exporting playlist: {e}")
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
            print(f"Error importing playlist: {e}")
            return False