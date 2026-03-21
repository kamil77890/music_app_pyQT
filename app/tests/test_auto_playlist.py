"""
Unit tests for AutoPlaylistManager — master «All Songs» playlist.
"""
import json
import os
import pytest
from unittest.mock import patch


@pytest.fixture
def tmp_library(tmp_path):
    return str(tmp_path)


def _create_dummy_audio(path: str, content: str = "dummy"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


def _make_playlist_json(folder: str, songs: list):
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "playlist.json"), "w") as f:
        json.dump({"name": os.path.basename(folder), "songs": songs, "version": "1.0"}, f)


class TestAutoPlaylistManager:

    def test_init_creates_default_playlist(self, tmp_library):
        from app.desktop.utils.auto_playlist import AutoPlaylistManager

        mgr = AutoPlaylistManager(tmp_library)
        assert os.path.isdir(mgr.get_folder())
        assert os.path.isfile(os.path.join(mgr.get_folder(), "playlist.json"))

    def test_add_song(self, tmp_library):
        from app.desktop.utils.auto_playlist import AutoPlaylistManager

        mgr = AutoPlaylistManager(tmp_library)

        fp = os.path.join(tmp_library, "test.mp3")
        _create_dummy_audio(fp)

        result = mgr.add_song(fp, {"title": "Test Song", "artist": "Test"})
        assert result is True

        songs = mgr.get_all_songs()
        assert len(songs) == 1
        assert songs[0]["title"] == "Test Song"

    def test_add_song_idempotent(self, tmp_library):
        from app.desktop.utils.auto_playlist import AutoPlaylistManager

        mgr = AutoPlaylistManager(tmp_library)
        fp = os.path.join(tmp_library, "test.mp3")
        _create_dummy_audio(fp)

        mgr.add_song(fp, {"title": "Song", "artist": "Artist"})
        result = mgr.add_song(fp, {"title": "Song", "artist": "Artist"})
        assert result is False

        assert len(mgr.get_all_songs()) == 1

    @patch("app.desktop.utils.metadata.get_audio_metadata",
           return_value={"title": "Found", "artist": "Auto", "duration": 0})
    def test_sync_from_library_finds_files_in_all_songs(
        self, mock_meta, tmp_library
    ):
        from app.desktop.utils.auto_playlist import AutoPlaylistManager

        mgr = AutoPlaylistManager(tmp_library)

        fp = os.path.join(mgr.get_folder(), "auto_song.mp3")
        _create_dummy_audio(fp)

        added = mgr.sync_from_library(tmp_library)
        assert added >= 1

        songs = mgr.get_all_songs()
        paths = [s["file_path"] for s in songs]
        assert fp in paths

    @patch("app.desktop.utils.metadata.get_audio_metadata",
           return_value={"title": "External", "artist": "Other", "duration": 0})
    def test_sync_from_library_finds_files_in_other_folders(
        self, mock_meta, tmp_library
    ):
        from app.desktop.utils.auto_playlist import AutoPlaylistManager

        mgr = AutoPlaylistManager(tmp_library)

        other_folder = os.path.join(tmp_library, "Other Playlist")
        fp = os.path.join(other_folder, "external.mp3")
        _create_dummy_audio(fp)

        added = mgr.sync_from_library(tmp_library)
        assert added >= 1

    def test_get_auto_playlist_manager_singleton(self, tmp_library):
        from app.desktop.utils.auto_playlist import (
            get_auto_playlist_manager, _manager,
        )

        mgr1 = get_auto_playlist_manager(tmp_library)
        mgr2 = get_auto_playlist_manager(tmp_library)
        assert mgr1 is mgr2

    def test_get_auto_playlist_manager_resets_on_path_change(self, tmp_path):
        from app.desktop.utils.auto_playlist import get_auto_playlist_manager

        path1 = str(tmp_path / "lib1")
        path2 = str(tmp_path / "lib2")
        os.makedirs(path1)
        os.makedirs(path2)

        mgr1 = get_auto_playlist_manager(path1)
        mgr2 = get_auto_playlist_manager(path2)
        assert mgr1 is not mgr2
