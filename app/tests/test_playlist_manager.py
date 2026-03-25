"""
Unit tests for PlaylistManager — JSON-based playlist CRUD.
"""
import json
import os
import pytest
import tempfile
import shutil


@pytest.fixture
def tmp_library(tmp_path):
    """Create a temporary library directory."""
    return str(tmp_path)


def _create_dummy_audio(path: str):
    """Create a minimal dummy file to simulate an audio file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("dummy audio")


class TestPlaylistManager:

    def test_create_playlist(self, tmp_library):
        from app.desktop.utils.playlist_manager import PlaylistManager

        folder = os.path.join(tmp_library, "My Playlist")
        result = PlaylistManager.create_playlist(folder, "My Playlist")
        assert result is True

        json_path = os.path.join(folder, "playlist.json")
        assert os.path.isfile(json_path)

        with open(json_path) as f:
            data = json.load(f)
        assert data["name"] == "My Playlist"
        assert data["songs"] == []

    def test_get_playlist_info_missing_json(self, tmp_library):
        from app.desktop.utils.playlist_manager import PlaylistManager

        folder = os.path.join(tmp_library, "empty")
        os.makedirs(folder, exist_ok=True)

        info = PlaylistManager.get_playlist_info(folder)
        assert info["name"] == "empty"
        assert info["songs"] == []

    def test_add_song_to_playlist(self, tmp_library):
        from app.desktop.utils.playlist_manager import PlaylistManager

        folder = os.path.join(tmp_library, "Test")
        PlaylistManager.create_playlist(folder, "Test")

        fp = os.path.join(tmp_library, "song.mp3")
        _create_dummy_audio(fp)

        result = PlaylistManager.add_song_to_playlist(
            folder, fp, {"title": "Hello", "artist": "World"})
        assert result is True

        info = PlaylistManager.get_playlist_info(folder)
        assert len(info["songs"]) == 1
        assert info["songs"][0]["title"] == "Hello"

    def test_add_song_idempotent(self, tmp_library):
        from app.desktop.utils.playlist_manager import PlaylistManager

        folder = os.path.join(tmp_library, "Test")
        PlaylistManager.create_playlist(folder, "Test")

        fp = os.path.join(tmp_library, "song.mp3")
        _create_dummy_audio(fp)

        PlaylistManager.add_song_to_playlist(
            folder, fp, {"title": "Song", "artist": "Artist"})
        result = PlaylistManager.add_song_to_playlist(
            folder, fp, {"title": "Song", "artist": "Artist"})
        assert result is False

        info = PlaylistManager.get_playlist_info(folder)
        assert len(info["songs"]) == 1

    def test_remove_song_from_playlist(self, tmp_library):
        from app.desktop.utils.playlist_manager import PlaylistManager

        folder = os.path.join(tmp_library, "Test")
        PlaylistManager.create_playlist(folder, "Test")

        fp = os.path.join(tmp_library, "song.mp3")
        _create_dummy_audio(fp)

        PlaylistManager.add_song_to_playlist(
            folder, fp, {"title": "S", "artist": "A"})
        result = PlaylistManager.remove_song_from_playlist(folder, 0)
        assert result is True

        info = PlaylistManager.get_playlist_info(folder)
        assert len(info["songs"]) == 0

    def test_remove_invalid_index(self, tmp_library):
        from app.desktop.utils.playlist_manager import PlaylistManager

        folder = os.path.join(tmp_library, "Test")
        PlaylistManager.create_playlist(folder, "Test")

        result = PlaylistManager.remove_song_from_playlist(folder, 99)
        assert result is False

    def test_get_all_playlists(self, tmp_library):
        from app.desktop.utils.playlist_manager import PlaylistManager

        for name in ["Rock", "Pop", "Jazz"]:
            folder = os.path.join(tmp_library, name)
            PlaylistManager.create_playlist(folder, name)

        playlists = PlaylistManager.get_all_playlists(tmp_library)
        names = {p["name"] for p in playlists}
        assert names == {"Rock", "Pop", "Jazz"}

    def test_get_all_playlists_expands_playlists_container(self, tmp_library):
        from app.desktop.utils.playlist_manager import PlaylistManager

        container = os.path.join(tmp_library, "playlists")
        os.makedirs(container)
        nested = os.path.join(container, "Inside")
        PlaylistManager.create_playlist(nested, "Inside")

        playlists = PlaylistManager.get_all_playlists(tmp_library)
        names = {p["name"] for p in playlists}
        paths = {os.path.normpath(p["folder_path"]) for p in playlists}
        assert "Inside" in names
        assert os.path.normpath(nested) in paths
        assert os.path.normpath(container) not in paths

    def test_ensure_default_playlist(self, tmp_library):
        from app.desktop.utils.playlist_manager import (
            PlaylistManager, DEFAULT_PLAYLIST_NAME,
        )

        folder = PlaylistManager.ensure_default_playlist(tmp_library)
        assert os.path.isdir(folder)
        assert os.path.basename(folder) == DEFAULT_PLAYLIST_NAME
        assert os.path.isfile(os.path.join(folder, "playlist.json"))

    def test_ensure_default_playlist_renames_legacy(self, tmp_library):
        from app.desktop.utils.playlist_manager import (
            PlaylistManager, DEFAULT_PLAYLIST_NAME, LEGACY_AUTO_PLAYLIST_FOLDER,
        )

        legacy = os.path.join(tmp_library, LEGACY_AUTO_PLAYLIST_FOLDER)
        os.makedirs(legacy)
        with open(os.path.join(legacy, "playlist.json"), "w") as f:
            json.dump({"name": "Legacy", "songs": []}, f)

        folder = PlaylistManager.ensure_default_playlist(tmp_library)
        assert os.path.basename(folder) == DEFAULT_PLAYLIST_NAME
        assert not os.path.exists(legacy)

    def test_is_default_playlist_folder(self, tmp_library):
        from app.desktop.utils.playlist_manager import (
            PlaylistManager, DEFAULT_PLAYLIST_NAME,
        )

        folder = PlaylistManager.ensure_default_playlist(tmp_library)
        assert PlaylistManager.is_default_playlist_folder(folder, tmp_library)
        assert not PlaylistManager.is_default_playlist_folder(
            os.path.join(tmp_library, "Other"), tmp_library)

    def test_sort_playlists_default_first(self, tmp_library):
        from app.desktop.utils.playlist_manager import (
            PlaylistManager, DEFAULT_PLAYLIST_NAME,
        )

        for name in ["Zebra", DEFAULT_PLAYLIST_NAME, "Alpha"]:
            folder = os.path.join(tmp_library, name)
            PlaylistManager.create_playlist(folder, name)

        playlists = PlaylistManager.get_all_playlists(tmp_library)
        sorted_pl = PlaylistManager.sort_playlists_default_first(
            playlists, tmp_library)
        assert sorted_pl[0]["name"] == DEFAULT_PLAYLIST_NAME

    def test_search_in_playlists(self, tmp_library):
        from app.desktop.utils.playlist_manager import PlaylistManager

        folder = os.path.join(tmp_library, "My Rock")
        PlaylistManager.create_playlist(folder, "My Rock")

        fp = os.path.join(tmp_library, "song.mp3")
        _create_dummy_audio(fp)
        PlaylistManager.add_song_to_playlist(
            folder, fp, {"title": "Thunderstruck", "artist": "AC/DC"})

        results = PlaylistManager.search_in_playlists(tmp_library, "thunder")
        assert len(results["songs"]) == 1
        assert results["songs"][0]["title"] == "Thunderstruck"

    def test_export_import_playlist(self, tmp_library):
        from app.desktop.utils.playlist_manager import PlaylistManager

        folder = os.path.join(tmp_library, "Export")
        PlaylistManager.create_playlist(folder, "Export")

        export_path = os.path.join(tmp_library, "exported.json")
        PlaylistManager.export_playlist(folder, export_path)
        assert os.path.isfile(export_path)

        import_folder = os.path.join(tmp_library, "Imported")
        PlaylistManager.import_playlist(export_path, import_folder)
        info = PlaylistManager.get_playlist_info(import_folder)
        assert info["name"] == "Export"
