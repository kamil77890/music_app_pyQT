import io

from fastapi.testclient import TestClient

from app.app import app


client = TestClient(app)


def test_download_library_invalid_url_has_standard_error_json():
    resp = client.post("/api/download-library", json={"url": "not-a-url"})

    assert resp.status_code == 400
    assert resp.headers.get("content-type", "").startswith("application/json")
    assert resp.json() == {
        "ok": False,
        "status": "failed",
        "error_code": "INVALID_URL",
        "message": "This is not a valid YouTube URL.",
    }


def test_download_library_ytdlp_429_has_standard_error_json(monkeypatch):
    import app.endpoints.library_api as lib_api

    def rate_limited(*args, **kwargs):
        from fastapi import HTTPException

        raise HTTPException(
            status_code=502,
            detail="YouTube rate-limited the download request",
            headers={"X-Error-Code": "YTDLP_RATE_LIMITED"},
        )

    monkeypatch.setattr(lib_api, "download_song", rate_limited)

    resp = client.post("/api/download-library", json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})

    assert resp.status_code == 502
    assert resp.json()["ok"] is False
    assert resp.json()["error_code"] == "YTDLP_RATE_LIMITED"


def test_library_stream_missing_file_uses_standard_json(monkeypatch, tmp_path):
    monkeypatch.setenv("MUSIC_LIBRARY_PATH", str(tmp_path))

    resp = client.get("/api/library/stream", params={"path": str(tmp_path / "missing.mp3")})

    assert resp.status_code == 404
    assert resp.json()["error_code"] == "FILE_NOT_FOUND"


def test_legacy_song_download_blocks_path_traversal(monkeypatch, tmp_path):
    from app.config.stałe import Parameters

    monkeypatch.setattr(Parameters, "get_download_dir", staticmethod(lambda: str(tmp_path)))

    resp = client.get("/songs/%2e%2e/%2e%2e/etc/passwd")

    assert resp.status_code in (400, 403)
    assert resp.headers.get("content-type", "").startswith("application/json")
    assert resp.json()["error_code"] == "PATH_TRAVERSAL_BLOCKED"


def test_subtitles_429_returns_json_not_stack_trace(monkeypatch):
    import app.endpoints.subtitles as subtitles_endpoint

    monkeypatch.setattr(
        subtitles_endpoint,
        "get_subtitles_as_txt",
        lambda *args, **kwargs: (_ for _ in ()).throw(Exception("HTTP Error 429: Too Many Requests")),
    )

    resp = client.get("/subtitles", params={"videoId": "dQw4w9WgXcQ", "lang": "pl"})

    assert resp.status_code in (429, 502)
    assert resp.headers.get("content-type", "").startswith("application/json")
    data = resp.json()
    assert data["ok"] is False
    assert data["error_code"] == "YTDLP_RATE_LIMITED"
    assert "Traceback" not in data["message"]


def test_upload_missing_file_returns_400_json():
    resp = client.post("/api/upload")

    assert resp.status_code == 400
    assert resp.headers.get("content-type", "").startswith("application/json")
    assert resp.json()["error_code"] == "MISSING_FIELD"


def test_upload_invalid_format_returns_400_json():
    resp = client.post(
        "/api/upload",
        files={"files": ("bad.txt", io.BytesIO(b"not audio"), "text/plain")},
    )

    assert resp.status_code == 400
    assert resp.json()["ok"] is False
    assert resp.json()["error_code"] == "INVALID_FILE_FORMAT"


def test_upload_valid_file_saves_to_library_and_cleans_temp(monkeypatch, tmp_path):
    import app.endpoints.upload as upload_endpoint

    temp_dir = tmp_path / "tmp"
    library_dir = tmp_path / "library"
    temp_dir.mkdir()
    library_dir.mkdir()
    saved_path = library_dir / "uploaded.mp3"

    monkeypatch.setattr(upload_endpoint.JellyfinConfig, "get_temp_dir", staticmethod(lambda: str(temp_dir)))
    monkeypatch.setattr(upload_endpoint.JellyfinConfig, "get_keep_legacy_copy", staticmethod(lambda: False))
    monkeypatch.setattr(upload_endpoint, "verify_metadata", lambda *args, **kwargs: {"title": "Uploaded", "artist": "Tester"})
    monkeypatch.setattr(upload_endpoint, "scan_music_files", lambda: [])
    monkeypatch.setattr(upload_endpoint, "build_and_save_playlist", lambda songs: {"songs": songs})
    monkeypatch.setattr(upload_endpoint, "sync_songs_to_db", lambda songs: 0)

    def fake_save(source_path, meta, copy=True):
        with open(source_path, "rb") as source:
            saved_path.write_bytes(source.read())
        return str(saved_path)

    monkeypatch.setattr(upload_endpoint, "saveTrackToLibrary", fake_save)

    resp = client.post(
        "/api/upload?rescan=false",
        files={"files": ("uploaded.mp3", io.BytesIO(b"fake mp3"), "audio/mpeg")},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["uploaded"] == 1
    assert data["files"][0]["jellyfin_path"] == str(saved_path)
    assert saved_path.exists()
    assert not (temp_dir / "uploaded.mp3").exists()


def test_upload_permission_error_returns_json(monkeypatch, tmp_path):
    import app.endpoints.upload as upload_endpoint

    monkeypatch.setattr(upload_endpoint.JellyfinConfig, "get_temp_dir", staticmethod(lambda: str(tmp_path)))
    monkeypatch.setattr(upload_endpoint.JellyfinConfig, "get_keep_legacy_copy", staticmethod(lambda: False))
    monkeypatch.setattr(upload_endpoint, "verify_metadata", lambda *args, **kwargs: {"title": "Uploaded"})
    monkeypatch.setattr(
        upload_endpoint,
        "saveTrackToLibrary",
        lambda *args, **kwargs: (_ for _ in ()).throw(PermissionError("denied")),
    )

    resp = client.post(
        "/api/upload?rescan=false",
        files={"files": ("uploaded.mp3", io.BytesIO(b"fake mp3"), "audio/mpeg")},
    )

    assert resp.status_code == 500
    assert resp.json()["error_code"] == "PERMISSION_DENIED"


def test_legacy_download_endpoint_accepts_download_song_dict(monkeypatch, tmp_path):
    import app.endpoints.download as download_endpoint

    audio_path = tmp_path / "song.mp3"
    audio_path.write_bytes(b"fake audio")

    monkeypatch.setattr(
        download_endpoint,
        "download_song",
        lambda *args, **kwargs: {"jellyfin_path": str(audio_path), "filepath": str(audio_path)},
    )
    monkeypatch.setattr(download_endpoint, "verify_metadata", lambda *args, **kwargs: {"title": "Song", "artist": "Artist"})
    monkeypatch.setattr(download_endpoint, "_refresh_recommendations_after_download", lambda: None)

    resp = client.get("/download", params={"videoId": "dQw4w9WgXcQ", "format": "mp3"})

    assert resp.status_code == 200
    assert resp.headers["x-jellyfin-path"] == str(audio_path)


def test_cors_options_download_library_allows_extension_request():
    resp = client.options(
        "/api/download-library",
        headers={
            "Origin": "moz-extension://test-extension",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert resp.status_code in (200, 204)
    assert resp.headers.get("access-control-allow-origin")
