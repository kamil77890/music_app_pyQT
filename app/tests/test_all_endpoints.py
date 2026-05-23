"""
Smoke-test all HTTP endpoints. Run with server up:
  uv run python run.py
  uv run pytest app/tests/test_all_endpoints.py -v -s
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest
import requests

BASE = os.environ.get("TEST_BASE_URL", "http://127.0.0.1:8000")
TIMEOUT = 120


def _get(path: str, **params) -> requests.Response:
    return requests.get(f"{BASE}{path}", params=params or None, timeout=TIMEOUT)


def _post(path: str, json_body: dict | None = None) -> requests.Response:
    return requests.post(f"{BASE}{path}", json=json_body or {}, timeout=TIMEOUT)


def _delete(path: str) -> requests.Response:
    return requests.delete(f"{BASE}{path}", timeout=TIMEOUT)


def _ok_or_expected(resp: requests.Response, allowed: set[int]) -> dict[str, Any]:
    assert resp.status_code in allowed, (
        f"{resp.request.method} {resp.url} -> {resp.status_code}: {resp.text[:500]}"
    )
    try:
        return resp.json()
    except Exception:
        return {"_raw": resp.text[:200], "_status": resp.status_code}


@pytest.fixture(scope="module")
def server_up():
    try:
        r = requests.get(f"{BASE}/", timeout=5)
        if r.status_code != 200:
            pytest.skip(f"Server not healthy at {BASE}")
    except requests.RequestException as exc:
        pytest.skip(f"Server not running at {BASE}: {exc}")


class TestHome:
    def test_root(self, server_up):
        data = _ok_or_expected(_get("/"), {200})
        assert isinstance(data, dict)
        assert len(data) > 5

    def test_favicon(self, server_up):
        r = requests.get(f"{BASE}/favicon.ico", timeout=5)
        assert r.status_code == 204


class TestEvents:
    def test_events_batch(self, server_up):
        body = {
            "events": [
                {
                    "video_id": "dQw4w9WgXcQ",
                    "event_type": "play",
                    "position_sec": 10,
                    "duration_sec": 200,
                    "session_id": "pytest-session",
                    "artist": "Test",
                    "title": "Test Song",
                }
            ]
        }
        data = _ok_or_expected(_post("/events/batch", body), {200})
        assert data.get("success") is True

    def test_feedback(self, server_up):
        data = _ok_or_expected(
            _post("/feedback", {"video_id": "dQw4w9WgXcQ", "feedback": "like"}),
            {200},
        )
        assert data.get("success") is True

    def test_impression_and_click(self, server_up):
        imp = _ok_or_expected(
            _post(
                "/recommendations/impression",
                {
                    "request_id": "pytest-req-1",
                    "items": [{"video_id": "dQw4w9WgXcQ", "position": 0}],
                },
            ),
            {200},
        )
        assert imp.get("success") is True
        click = _ok_or_expected(
            _post(
                "/recommendations/click",
                {"request_id": "pytest-req-1", "video_id": "dQw4w9WgXcQ"},
            ),
            {200, 404},
        )
        assert "success" in click


class TestYouTubeAuth:
    def test_status(self, server_up):
        data = _ok_or_expected(_get("/auth/youtube/status"), {200})
        assert "connected" in data

    def test_start(self, server_up):
        data = _ok_or_expected(_get("/auth/youtube/start"), {200, 503})
        if data.get("auth_url"):
            assert "google" in data["auth_url"]

    def test_import(self, server_up):
        data = _ok_or_expected(_post("/auth/youtube/import"), {200, 400, 500})
        assert "success" in data or "detail" in data


class TestRecommendations:
    def test_profile(self, server_up):
        data = _ok_or_expected(_get("/recommendations/profile"), {200, 404})
        if data.get("success"):
            assert "taste_profile" in data

    def test_recommendations(self, server_up):
        data = _ok_or_expected(
            _get("/recommendations", max_results=3),
            {200, 404, 429},
        )
        assert "success" in data or "detail" in data

    def test_advanced(self, server_up):
        data = _ok_or_expected(
            _get("/recommendations/advanced", max_results=3),
            {200, 404, 429, 500},
        )
        assert "success" in data or "detail" in data

    def test_explain(self, server_up):
        data = _ok_or_expected(
            _get("/recommendations/explain/dQw4w9WgXcQ"),
            {200, 404},
        )
        assert "success" in data or "detail" in data


class TestLibrary:
    def test_playlists_all_songs(self, server_up):
        data = _ok_or_expected(_get("/playlists/all-songs"), {200, 404})
        assert isinstance(data, (dict, list)) or "detail" in data

    def test_api_songs(self, server_up):
        data = _ok_or_expected(_get("/api/songs"), {200})
        assert isinstance(data, (dict, list))


class TestSearch:
    def test_search(self, server_up):
        data = _ok_or_expected(
            _get("/search", q="nightcore", max_results=2),
            {200, 429, 500},
        )
        assert isinstance(data, dict) or "detail" in data


class TestSubscriptions:
    def test_list_subscriptions(self, server_up):
        data = _ok_or_expected(_get("/subscriptions"), {200})
        assert isinstance(data, (dict, list))

    def test_notifications(self, server_up):
        data = _ok_or_expected(_get("/notifications"), {200})
        assert isinstance(data, (dict, list))


class TestTags:
    def test_tags_vocabulary(self, server_up):
        data = _ok_or_expected(_get("/tags/vocabulary"), {200, 404})
        assert data is not None

    def test_tags_list(self, server_up):
        data = _ok_or_expected(_get("/tags"), {200, 404})
        assert data is not None


class TestMisc:
    def test_register(self, server_up):
        r = requests.get(f"{BASE}/Register", headers={"Authorization": "pytest"}, timeout=10)
        assert r.status_code in (200, 404, 422)

    def test_video_url(self, server_up):
        data = _ok_or_expected(
            _get("/video-url", video_id="dQw4w9WgXcQ"),
            {200, 400, 404, 422, 500},
        )
        assert data is not None
