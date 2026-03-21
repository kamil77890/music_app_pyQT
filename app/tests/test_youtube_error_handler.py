"""
Unit tests for youtube_error_handler — sync/async decorator with key rotation.
"""
import asyncio
import os
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def _set_api_keys(monkeypatch):
    monkeypatch.setenv("API_KEY", "key-A")
    monkeypatch.setenv("API_KEY_2", "key-B")
    monkeypatch.setenv("ACTIVE_API_KEY_INDEX", "0")


def _make_http_error(status: int, content: str):
    """Create a mock HttpError."""
    err = MagicMock()
    err.resp = MagicMock()
    err.resp.status = status
    err.content = content.encode("utf-8")
    err.__class__ = type("HttpError", (Exception,), {})
    return err


class TestHandleYoutubeApiError:

    def test_quota_exceeded_switches_key(self, monkeypatch):
        from app.utils.api_key_manager import APIKeyManager
        mgr = APIKeyManager()
        monkeypatch.setattr(
            "app.utils.youtube_error_handler.api_key_manager", mgr)
        from app.utils.youtube_error_handler import handle_youtube_api_error
        from googleapiclient.errors import HttpError

        resp = MagicMock()
        resp.status = 403
        error = HttpError(resp, b'quotaExceeded')

        handle_youtube_api_error(error)
        assert mgr.current_index == 1

    def test_quota_exceeded_all_keys_raises(self, monkeypatch):
        from app.utils.api_key_manager import APIKeyManager
        mgr = APIKeyManager()
        mgr._exhausted = {0, 1}
        monkeypatch.setattr(
            "app.utils.youtube_error_handler.api_key_manager", mgr)
        from app.utils.youtube_error_handler import handle_youtube_api_error
        from app.exceptions.youtube_errors import YouTubeQuotaExceededError
        from googleapiclient.errors import HttpError

        resp = MagicMock()
        resp.status = 403
        error = HttpError(resp, b'quotaExceeded')

        with pytest.raises(YouTubeQuotaExceededError):
            handle_youtube_api_error(error)

    def test_403_non_quota_raises_access_denied(self, monkeypatch):
        from app.utils.api_key_manager import APIKeyManager
        mgr = APIKeyManager()
        monkeypatch.setattr(
            "app.utils.youtube_error_handler.api_key_manager", mgr)
        from app.utils.youtube_error_handler import handle_youtube_api_error
        from app.exceptions.youtube_errors import YouTubeAccessDeniedError
        from googleapiclient.errors import HttpError

        resp = MagicMock()
        resp.status = 403
        error = HttpError(resp, b'accessDenied')

        with pytest.raises(YouTubeAccessDeniedError):
            handle_youtube_api_error(error)

    def test_404_raises_not_found(self, monkeypatch):
        from app.utils.api_key_manager import APIKeyManager
        mgr = APIKeyManager()
        monkeypatch.setattr(
            "app.utils.youtube_error_handler.api_key_manager", mgr)
        from app.utils.youtube_error_handler import handle_youtube_api_error
        from app.exceptions.youtube_errors import YouTubeNotFoundError
        from googleapiclient.errors import HttpError

        resp = MagicMock()
        resp.status = 404
        error = HttpError(resp, b'not found')

        with pytest.raises(YouTubeNotFoundError):
            handle_youtube_api_error(error)


class TestDecoratorSync:

    def test_sync_function_retries_on_quota(self, monkeypatch):
        from app.utils.api_key_manager import APIKeyManager
        mgr = APIKeyManager()
        monkeypatch.setattr(
            "app.utils.youtube_error_handler.api_key_manager", mgr)
        from app.utils.youtube_error_handler import youtube_api_error_handler
        from googleapiclient.errors import HttpError

        call_count = 0

        @youtube_api_error_handler
        def my_func():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                resp = MagicMock()
                resp.status = 403
                raise HttpError(resp, b'quotaExceeded')
            return "success"

        result = my_func()
        assert result == "success"
        assert call_count == 2


class TestDecoratorAsync:

    def test_async_function_retries_on_quota(self, monkeypatch):
        from app.utils.api_key_manager import APIKeyManager
        mgr = APIKeyManager()
        monkeypatch.setattr(
            "app.utils.youtube_error_handler.api_key_manager", mgr)
        from app.utils.youtube_error_handler import youtube_api_error_handler
        from googleapiclient.errors import HttpError

        call_count = 0

        @youtube_api_error_handler
        async def my_async_func():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                resp = MagicMock()
                resp.status = 403
                raise HttpError(resp, b'quotaExceeded')
            return "async_success"

        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(my_async_func())
        loop.close()

        assert result == "async_success"
        assert call_count == 2

    def test_async_decorator_preserves_coroutine(self, monkeypatch):
        from app.utils.api_key_manager import APIKeyManager
        mgr = APIKeyManager()
        monkeypatch.setattr(
            "app.utils.youtube_error_handler.api_key_manager", mgr)
        from app.utils.youtube_error_handler import youtube_api_error_handler

        @youtube_api_error_handler
        async def my_coro():
            return 42

        assert asyncio.iscoroutinefunction(my_coro)
