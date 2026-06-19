import os
import stat

from app.config.jellyfin_config import JellyfinConfig
from app.logic.jellyfin_library import (
    sanitize_component,
    _safe_path,
    _resolve_duplicate,
    _set_permissions,
    saveTrackToLibrary,
)


class TestSanitizeComponent:
    def test_removes_dangerous_chars(self):
        result = sanitize_component(r'Artist / Name : Test * ? " < > |')
        assert "/" not in result
        assert "\\" not in result
        assert ":" not in result
        assert "*" not in result
        assert "?" not in result
        assert '"' not in result
        assert "<" not in result
        assert ">" not in result
        assert "|" not in result

    def test_removes_control_chars(self):
        result = sanitize_component("Test\x00\x01\x02Song")
        assert result == "TestSong"

    def test_collapses_multiple_spaces(self):
        result = sanitize_component("Artist    Name")
        assert result == "Artist Name"

    def test_strips_whitespace(self):
        result = sanitize_component("  Hello  ")
        assert result == "Hello"

    def test_empty_fallback(self):
        result = sanitize_component("")
        assert result == "_"

    def test_truncates_long_names(self):
        long_name = "A" * 500
        result = sanitize_component(long_name, max_len=100)
        assert len(result) <= 100

    def test_strips_trailing_dots_and_spaces(self):
        result = sanitize_component("Artist... ")
        assert not result.endswith(".")


class TestSafePath:
    def test_normal_path(self, tmp_path):
        lib = str(tmp_path / "music")
        result = _safe_path(lib, "Daft Punk", "Random Access Memories", "01 - Song.mp3")
        assert str(result) == os.path.join(lib, "Daft Punk", "Random Access Memories", "01 - Song.mp3")

    def test_sanitizes_components(self, tmp_path):
        lib = str(tmp_path / "music")
        result = _safe_path(lib, "Bad / Artist", "Album: Test", "01 - Song.mp3")
        assert "Bad / Artist" not in str(result)
        assert "Album: Test" not in str(result)

    def test_prevents_path_traversal(self, tmp_path):
        lib = str(tmp_path / "music")
        result = _safe_path(lib, "..", "..", "evil.mp3")
        assert str(result).startswith(os.path.realpath(lib))

    def test_prevents_traversal_in_filename(self, tmp_path):
        lib = str(tmp_path / "music")
        result = _safe_path(lib, "Artist", "Album", "../../evil.mp3")
        assert str(result).startswith(os.path.realpath(lib))

    def test_fallback_to_unknown_artist_and_album(self, tmp_path):
        lib = str(tmp_path / "music")
        result = _safe_path(lib, "", "", "song.mp3")
        assert "Unknown Artist" in str(result) or "_" in str(result)
        assert "Unknown Album" in str(result) or "_" in str(result)


class TestResolveDuplicate:
    def test_no_duplicate(self, tmp_path):
        p = tmp_path / "Song.mp3"
        result = _resolve_duplicate(p)
        assert result == p

    def test_adds_suffix_on_duplicate(self, tmp_path):
        p = tmp_path / "Song.mp3"
        p.touch()
        result = _resolve_duplicate(p)
        assert result != p
        assert "Song (1)" in result.name

    def test_increments_suffix(self, tmp_path):
        p = tmp_path / "Song.mp3"
        p.touch()
        (tmp_path / "Song (1).mp3").touch()
        result = _resolve_duplicate(p)
        assert "Song (2)" in result.name


class TestSetPermissions:
    def test_file_permissions(self, tmp_path):
        f = tmp_path / "test.mp3"
        f.touch()
        _set_permissions(f)
        st = f.stat()
        assert st.st_mode & stat.S_IRUSR
        assert st.st_mode & stat.S_IWUSR
        assert st.st_mode & stat.S_IRGRP

    def test_dir_permissions(self, tmp_path):
        d = tmp_path / "testdir"
        d.mkdir()
        _set_permissions(d)
        st = d.stat()
        assert st.st_mode & stat.S_IRWXU
        assert st.st_mode & stat.S_IRGRP
        assert st.st_mode & stat.S_IXGRP

    def test_fallback_on_missing_path(self, tmp_path):
        f = tmp_path / "nonexistent.mp3"
        _set_permissions(f)


class TestUnknownFallback:
    def test_unknown_artist_in_metadata(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MUSIC_LIBRARY_PATH", str(tmp_path / "music"))

        song = tmp_path / "song.mp3"
        song.write_text("fake mp3 data")

        result = saveTrackToLibrary(
            str(song),
            {"title": "Test Song"},
        )
        assert "Unknown Artist" in result
        assert "Unknown Album" in result

    def test_unknown_album_in_metadata(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MUSIC_LIBRARY_PATH", str(tmp_path / "music"))

        song = tmp_path / "test.mp3"
        song.write_text("fake mp3 data")

        result = saveTrackToLibrary(
            str(song),
            {"title": "Test", "artist": "Test Artist"},
        )
        assert "Test Artist" in result
        assert "Unknown Album" in result


class TestFormatAndStructure:
    def test_track_number_prefix_in_filename(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MUSIC_LIBRARY_PATH", str(tmp_path / "music"))

        song = tmp_path / "song.mp3"
        song.write_text("fake")
        result = saveTrackToLibrary(
            str(song),
            {
                "title": "Test Song",
                "artist": "Test Artist",
                "album": "Test Album",
                "trackNumber": "1",
            },
        )
        assert "01 - Test Song.mp3" in result
        assert "Test Artist" in result
        assert "Test Album" in result

    def test_structure_artist_album_track(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MUSIC_LIBRARY_PATH", str(tmp_path / "music"))

        song = tmp_path / "input.mp3"
        song.write_text("fake")
        result = saveTrackToLibrary(
            str(song),
            {
                "title": "My Song",
                "artist": "My Artist",
                "album": "My Album",
                "trackNumber": "5",
            },
        )
        rel = os.path.relpath(result, str(tmp_path / "music"))
        assert rel == os.path.join("My Artist", "My Album", "05 - My Song.mp3")


class TestSafety:
    def test_path_traversal_blocked(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MUSIC_LIBRARY_PATH", str(tmp_path / "music"))

        song = tmp_path / "song.mp3"
        song.write_text("fake")

        result = saveTrackToLibrary(
            str(song),
            {
                "title": "../../evil",
                "artist": "../../evil",
            },
        )
        lib = str(tmp_path / "music")
        assert os.path.commonpath([result, lib]) == os.path.normpath(lib)

    def test_all_files_in_library_path(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MUSIC_LIBRARY_PATH", str(tmp_path / "music"))

        song = tmp_path / "song.mp3"
        song.write_text("fake")

        result = saveTrackToLibrary(
            str(song),
            {"title": "Safe", "artist": "Safe Artist", "album": "Safe Album"},
        )
        lib = str(tmp_path / "music")
        assert os.path.commonpath([result, lib]) == os.path.normpath(lib)


class TestPermissionsFallback:
    def test_no_crash_on_chmod_failure(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MUSIC_LIBRARY_PATH", str(tmp_path / "music"))

        song = tmp_path / "song.mp3"
        song.write_text("fake")
        os.chmod(str(tmp_path), stat.S_IRWXU)

        result = saveTrackToLibrary(
            str(song),
            {"title": "Test", "artist": "Test Artist"},
        )
        assert os.path.exists(result)


class TestFormatKeep:
    def test_keep_does_not_convert(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MUSIC_LIBRARY_PATH", str(tmp_path / "music"))
        monkeypatch.setenv("MUSIC_OUTPUT_FORMAT", "keep")

        song = tmp_path / "test.flac"
        song.write_text("fake flac content")
        result = saveTrackToLibrary(
            str(song),
            {"title": "Test", "artist": "Test Artist"},
        )
        assert result.endswith(".flac"), f"Expected .flac, got {result}"

    def test_format_mp3_without_ffmpeg_fallback(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MUSIC_LIBRARY_PATH", str(tmp_path / "music"))
        monkeypatch.setenv("MUSIC_OUTPUT_FORMAT", "mp3")

        song = tmp_path / "test.flac"
        song.write_text("fake flac content")
        result = saveTrackToLibrary(
            str(song),
            {"title": "Test", "artist": "Test Artist"},
        )
        assert os.path.exists(result)


class TestJellyfinConfig:
    def test_keep_legacy_copy_default_false(self):
        saved = os.environ.pop("MUSIC_KEEP_LEGACY_COPY", None)
        try:
            assert JellyfinConfig.get_keep_legacy_copy() is False
        finally:
            if saved is not None:
                os.environ["MUSIC_KEEP_LEGACY_COPY"] = saved

    def test_keep_legacy_copy_true(self, monkeypatch):
        monkeypatch.setenv("MUSIC_KEEP_LEGACY_COPY", "true")
        assert JellyfinConfig.get_keep_legacy_copy() is True

    def test_keep_legacy_copy_parses_1(self, monkeypatch):
        monkeypatch.setenv("MUSIC_KEEP_LEGACY_COPY", "1")
        assert JellyfinConfig.get_keep_legacy_copy() is True

    def test_temp_path_default_empty(self):
        saved = os.environ.pop("MUSIC_TEMP_PATH", None)
        try:
            assert JellyfinConfig.get_temp_path() == ""
        finally:
            if saved is not None:
                os.environ["MUSIC_TEMP_PATH"] = saved

    def test_temp_dir_default_uses_filepath_dot_tmp(self, monkeypatch):
        monkeypatch.setenv("FILEPATH", "/tmp/test_music")
        # must clear MUSIC_TEMP_PATH so default kicks in
        monkeypatch.delenv("MUSIC_TEMP_PATH", raising=False)
        result = JellyfinConfig.get_temp_dir()
        assert result == "/tmp/test_music/.tmp"


class TestSaveTrackToLibraryCopyFalse:
    def test_copy_false_saves_to_library(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MUSIC_LIBRARY_PATH", str(tmp_path / "music"))
        monkeypatch.setenv("MUSIC_OUTPUT_FORMAT", "keep")

        source = tmp_path / "source.mp3"
        source.write_text("fake mp3 data")

        result = saveTrackToLibrary(
            str(source),
            {"title": "Test", "artist": "Test Artist", "album": "Test Album", "trackNumber": "1"},
            copy=False,
        )
        assert os.path.isfile(result), f"Expected file at {result}"
        assert "Test Artist" in result
        assert "Test Album" in result
        assert "01 - Test" in result

    def test_copy_false_leaves_source_intact(self, tmp_path, monkeypatch):
        """saveTrackToLibrary(copy=False) does NOT delete the source file."""
        monkeypatch.setenv("MUSIC_LIBRARY_PATH", str(tmp_path / "music"))
        monkeypatch.setenv("MUSIC_OUTPUT_FORMAT", "keep")

        source = tmp_path / "source.mp3"
        source.write_text("fake mp3 data")

        saveTrackToLibrary(
            str(source),
            {"title": "Test", "artist": "Test Artist", "album": "Test Album"},
            copy=False,
        )
        assert os.path.isfile(source), "Source must NOT be deleted by saveTrackToLibrary"


class TestJellyfinScan:
    def test_no_api_key_skips_scan(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MUSIC_LIBRARY_PATH", str(tmp_path / "music"))
        monkeypatch.setenv("JELLYFIN_API_KEY", "")

        song = tmp_path / "song.mp3"
        song.write_text("fake")
        result = saveTrackToLibrary(
            str(song),
            {"title": "Test", "artist": "Test Artist"},
        )
        assert os.path.exists(result)

    def test_scan_graceful_without_key(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MUSIC_LIBRARY_PATH", str(tmp_path / "music"))
        monkeypatch.setenv("JELLYFIN_API_KEY", "")

        song = tmp_path / "song.mp3"
        song.write_text("fake")
        result = saveTrackToLibrary(str(song), {"title": "Test", "artist": "Test Artist"})
        assert os.path.exists(result)

    def test_auto_scan_false_skips_scan_even_with_key(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MUSIC_LIBRARY_PATH", str(tmp_path / "music"))
        monkeypatch.setenv("JELLYFIN_API_KEY", "some-key")
        monkeypatch.setenv("JELLYFIN_AUTO_SCAN", "false")

        call_count = 0

        def _fake_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1

        monkeypatch.setattr("requests.post", _fake_post)

        song = tmp_path / "song.mp3"
        song.write_text("fake")
        result = saveTrackToLibrary(str(song), {"title": "Test", "artist": "Test Artist"})
        assert os.path.exists(result)
        assert call_count == 0, "requests.post was called even though AUTO_SCAN=false"

    def test_scan_request_made_when_api_key_set(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MUSIC_LIBRARY_PATH", str(tmp_path / "music"))
        monkeypatch.setenv("JELLYFIN_API_KEY", "test-key-123")
        monkeypatch.setenv("JELLYFIN_AUTO_SCAN", "true")
        monkeypatch.setenv("JELLYFIN_URL", "http://localhost:9999")

        call_data = {}

        def _fake_post(url, headers=None, timeout=30, **kwargs):
            call_data["url"] = url
            call_data["token"] = (headers or {}).get("X-Emby-Token")
            from unittest.mock import MagicMock
            resp = MagicMock()
            resp.status_code = 204
            return resp

        monkeypatch.setattr("requests.post", _fake_post)

        song = tmp_path / "song.mp3"
        song.write_text("fake")
        result = saveTrackToLibrary(str(song), {"title": "Test", "artist": "Test Artist"})
        assert os.path.exists(result)
        assert call_data.get("url") == "http://localhost:9999/Library/Refresh"
        assert call_data.get("token") == "test-key-123", "API key not sent as X-Emby-Token"

    def test_scan_request_error_does_not_crash_save(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MUSIC_LIBRARY_PATH", str(tmp_path / "music"))
        monkeypatch.setenv("JELLYFIN_API_KEY", "test-key-123")
        monkeypatch.setenv("JELLYFIN_AUTO_SCAN", "true")

        import requests
        def _failing_post(*args, **kwargs):
            raise requests.exceptions.ConnectionError("Jellyfin not reachable")

        monkeypatch.setattr("requests.post", _failing_post)

        song = tmp_path / "song.mp3"
        song.write_text("fake")
        result = saveTrackToLibrary(str(song), {"title": "Test", "artist": "Test Artist"})
        assert os.path.exists(result), "File must be saved even when Jellyfin scan fails"
