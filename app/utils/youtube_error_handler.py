"""
YouTube API error handler + decorator with automatic key rotation on quotaExceeded.
Handles both sync and async functions.
"""
from __future__ import annotations

import asyncio
import functools
import logging

from googleapiclient.errors import HttpError

log = logging.getLogger(__name__)

from app.exceptions.youtube_errors import (
    YouTubeQuotaExceededError,
    YouTubeAccessDeniedError,
    YouTubeNotFoundError,
    YouTubeBadRequestError,
    YouTubeServerError,
    YouTubeAPIError,
)
from app.utils.api_key_manager import api_key_manager


def handle_youtube_api_error(error: HttpError) -> None:
    """
    Inspect an HttpError and either:
      • switch API keys + return (caller should retry), or
      • raise a typed exception.
    """
    status_code = error.resp.status
    body = error.content.decode("utf-8") if error.content else str(error)

    if status_code == 403:
        if "quotaExceeded" in body or "rateLimitExceeded" in body:
            if api_key_manager.has_available_keys():
                try:
                    api_key_manager.switch_to_next_key()
                    return  # signal: retry
                except RuntimeError:
                    pass
            raise YouTubeQuotaExceededError(error)
        raise YouTubeAccessDeniedError(error)

    if status_code == 404:
        raise YouTubeNotFoundError("Requested resource", error)
    if status_code == 400:
        raise YouTubeBadRequestError("Bad request parameters", error)
    if status_code >= 500:
        raise YouTubeServerError(error)

    raise YouTubeAPIError(f"YouTube API error {status_code}: {body}", error)


def youtube_api_error_handler(func):
    """
    Decorator that catches HttpError, rotates keys on quota errors,
    and retries.  Works for both sync and async functions.
    """
    max_attempts = len(api_key_manager.keys)

    if asyncio.iscoroutinefunction(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except HttpError as e:
                    try:
                        handle_youtube_api_error(e)
                        log.info("Retrying with new key (attempt %d/%d)", attempt, max_attempts)
                        continue
                    except YouTubeAPIError:
                        if attempt >= max_attempts:
                            raise
                        log.warning("API error on attempt %d/%d", attempt, max_attempts)
                        continue
            raise YouTubeAPIError(f"Max retries ({max_attempts}) exceeded")
        return async_wrapper
    else:
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except HttpError as e:
                    try:
                        handle_youtube_api_error(e)
                        log.info("Retrying with new key (attempt %d/%d)", attempt, max_attempts)
                        continue
                    except YouTubeAPIError:
                        if attempt >= max_attempts:
                            raise
                        log.warning("API error on attempt %d/%d", attempt, max_attempts)
                        continue
            raise YouTubeAPIError(f"Max retries ({max_attempts}) exceeded")
        return sync_wrapper
