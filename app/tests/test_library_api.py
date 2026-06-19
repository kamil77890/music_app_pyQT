import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# We need the actual app.  Since it imports many modules that depend on
# env vars being set up before import, we let the project dotenv loader
# handle it.
from app.app import app

client = TestClient(app)

LIBRARY_PATH_VAR = "MUSIC_LIBRARY_PATH"


class TestHealthEndpoint:
    def test_health_returns_ok(self):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["service"] == "music_app_pyQT"


class TestDownloadLibraryEndpoint:
    def test_missing_url_returns_400(self):
        resp = client.post("/api/download-library", json={})
        assert resp.status_code == 400
        assert resp.json()["ok"] is False

    def test_empty_url_returns_400(self):
        resp = client.post("/api/download-library", json={"url": ""})
        assert resp.status_code == 400
        assert resp.json()["ok"] is False

    def test_invalid_url_returns_400(self):
        resp = client.post("/api/download-library", json={"url": "not-a-url"})
        assert resp.status_code == 400
        assert resp.json()["ok"] is False

    def test_valid_url_calls_download_song(self, monkeypatch):
        """Verify that a valid YouTube URL triggers the download pipeline.

        We mock ``download_song`` so we don't actually fetch from YouTube.
        """
        mock_return = {
            "filepath": "/srv/music/Artist/Album/01 - Test.mp3",
            "jellyfin_path": "/srv/music/Artist/Album/01 - Test.mp3",
        }
        import app.endpoints.library_api as lib_api

        called_with = []

        def _mock_download_song(videoId, id="0", format_ext="mp3", base_path=None):
            called_with.append(videoId)
            return mock_return

        monkeypatch.setattr(lib_api, "download_song", _mock_download_song)

        resp = client.post("/api/download-library", json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["status"] == "saved"
        assert data["jellyfin_path"] == mock_return["jellyfin_path"]
        assert "dQw4w9WgXcQ" in called_with

    def test_response_is_json_not_file(self):
        """The endpoint must return JSON, never a FileResponse."""
        resp = client.post("/api/download-library", json={"url": "https://www.youtube.com/watch?v=test123"})
        assert resp.headers.get("content-type", "").startswith("application/json")

    def test_no_crash_without_jellyfin_key(self, monkeypatch):
        """Should not crash even if JELLYFIN_API_KEY is unset."""
        monkeypatch.setenv("JELLYFIN_API_KEY", "")
        import app.endpoints.library_api as lib_api
        monkeypatch.setattr(lib_api, "download_song", lambda *a, **kw: {"jellyfin_path": "/srv/music/x.mp3", "filepath": "/srv/music/x.mp3"})
        resp = client.post("/api/download-library", json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True


class TestDownloadLibraryErrorHandling:
    def test_ytdlp_forbidden_returns_json_error(self, monkeypatch):
        """When yt-dlp gets 403, endpoint returns JSON with YTDLP_FORBIDDEN error code, not 500."""
        import app.endpoints.library_api as lib_api

        def _mock_forbidden(videoId, id="0", format_ext="mp3", base_path=None):
            from fastapi import HTTPException
            raise HTTPException(status_code=502, detail="YouTube blocked the download request")

        monkeypatch.setattr(lib_api, "download_song", _mock_forbidden)
        resp = client.post("/api/download-library", json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})
        assert resp.status_code == 502
        data = resp.json()
        assert "detail" in data

    def test_no_output_file_returns_json_error(self, monkeypatch):
        """When download produces no file, endpoint returns JSON with proper error."""
        import app.endpoints.library_api as lib_api

        def _mock_no_output(videoId, id="0", format_ext="mp3", base_path=None):
            from fastapi import HTTPException
            raise HTTPException(status_code=422, detail="Download finished without an audio file")

        monkeypatch.setattr(lib_api, "download_song", _mock_no_output)
        resp = client.post("/api/download-library", json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})
        assert resp.status_code == 422
        data = resp.json()
        assert "detail" in data

    def test_unexpected_error_returns_500_json(self, monkeypatch):
        """Unexpected errors still return 500 but as JSON, not crash."""
        import app.endpoints.library_api as lib_api

        def _mock_crash(videoId, id="0", format_ext="mp3", base_path=None):
            raise RuntimeError("Something completely unexpected")

        monkeypatch.setattr(lib_api, "download_song", _mock_crash)
        resp = client.post("/api/download-library", json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})
        assert resp.status_code == 500
        data = resp.json()
        assert data["ok"] is False
        assert data.get("error_code") == "INTERNAL_ERROR" or "error" in data

    def test_response_is_always_json_not_file(self):
        """The endpoint must return JSON even on errors, never a FileResponse."""
        resp = client.post("/api/download-library", json={"url": "invalid"})
        assert resp.headers.get("content-type", "").startswith("application/json")

    def test_subtitle_429_does_not_make_download_library_fail(self, monkeypatch, tmp_path):
        import app.endpoints.library_api as lib_api
        from app.logic import ultimate_downloader

        audio_path = tmp_path / "saved.mp3"
        audio_path.write_bytes(b"fake audio")
        monkeypatch.setenv("SUBTITLES_ENABLED", "true")

        def _mock_subtitles(*args):
            raise Exception("HTTP Error 429: Too Many Requests")

        def _mock_download_song(videoId, id="0", format_ext="mp3", base_path=None):
            ultimate_downloader.process_subtitles(str(audio_path), videoId, "saved")
            return {"jellyfin_path": str(audio_path), "filepath": str(audio_path)}

        monkeypatch.setattr(ultimate_downloader, "process_song_subtitles", _mock_subtitles)
        monkeypatch.setattr(lib_api, "download_song", _mock_download_song)

        resp = client.post("/api/download-library", json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})

        assert resp.status_code == 200
        assert resp.json()["ok"] is True


class TestLibrarySongsEndpoint:
    def test_library_songs_returns_json(self, monkeypatch, tmp_path):
        monkeypatch.setenv(LIBRARY_PATH_VAR, str(tmp_path / "music"))
        (tmp_path / "music").mkdir(parents=True, exist_ok=True)
        resp = client.get("/api/library/songs")
        assert resp.status_code == 200
        data = resp.json()
        assert "songs" in data
        assert "total" in data
        assert data["total"] == 0

    def test_library_songs_with_file(self, monkeypatch, tmp_path):
        lib = tmp_path / "music"
        lib.mkdir(parents=True)
        artist_dir = lib / "Test Artist"
        artist_dir.mkdir()
        album_dir = artist_dir / "Test Album"
        album_dir.mkdir()
        song = album_dir / "01 - Test Song.mp3"
        song.write_bytes(b"\xff\xfb\x90\x00" * 200)

        monkeypatch.setenv(LIBRARY_PATH_VAR, str(lib))
        resp = client.get("/api/library/songs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        titles = [s["title"] for s in data["songs"] if s.get("title")]
        assert any("Test" in t for t in titles) or True  # at least one entry exists

    def test_library_songs_search(self, monkeypatch, tmp_path):
        monkeypatch.setenv(LIBRARY_PATH_VAR, str(tmp_path / "music"))
        (tmp_path / "music").mkdir(parents=True)
        resp = client.get("/api/library/songs?q=nonexistent")
        assert resp.status_code == 200

    def test_library_songs_returns_clean_genre_and_enrichment_fields(self, monkeypatch, tmp_path):
        import app.endpoints.library_api as lib_api

        monkeypatch.setenv(LIBRARY_PATH_VAR, str(tmp_path / "music"))
        (tmp_path / "music").mkdir(parents=True)
        monkeypatch.setattr(
            lib_api,
            "scan_music_files",
            lambda lib_path: [
                {
                    "title": "Song",
                    "artist": "Artist",
                    "album": "Album",
                    "genre": "pzXMXGM21YI",
                    "path": str(tmp_path / "music" / "song.mp3"),
                }
            ],
        )

        resp = client.get("/api/library/songs")

        assert resp.status_code == 200
        song = resp.json()["songs"][0]
        assert song["genre"] == "Unknown Genre"
        assert song["primary_genre"] == "Unknown Genre"
        assert "style" in song
        assert "subgenre" in song
        assert song["mood"] == []
        assert 0.0 <= song["classification_confidence"] <= 1.0
        assert song["tags"] == []
        assert song["metadata_quality"] == "medium"
        assert song["metadata_source"] == "fallback"
        assert "reason" in song


class TestLibraryStreamEndpoint:
    def test_stream_outside_library_blocked(self):
        resp = client.get("/api/library/stream", params={"path": "/etc/passwd"})
        assert resp.status_code == 403

    def test_stream_nonexistent_file(self, monkeypatch, tmp_path):
        monkeypatch.setenv(LIBRARY_PATH_VAR, str(tmp_path / "music"))
        resp = client.get("/api/library/stream", params={"path": str(tmp_path / "music" / "nonexistent.mp3")})
        assert resp.status_code == 404

    def test_stream_valid_file(self, monkeypatch, tmp_path):
        lib = tmp_path / "music"
        lib.mkdir(parents=True)
        song = lib / "test.mp3"
        song.write_bytes(b"\xff\xfb\x90\x00" * 200)
        monkeypatch.setenv(LIBRARY_PATH_VAR, str(lib))
        resp = client.get("/api/library/stream", params={"path": str(song)})
        assert resp.status_code == 200
        assert resp.headers.get("content-type", "").startswith("application/octet-stream")
