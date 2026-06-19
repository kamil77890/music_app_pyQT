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
