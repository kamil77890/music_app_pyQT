"""
YouTube API key manager — rotates through configured keys when quota is exceeded.
Tracks exhausted keys per-session so we never retry a known-spent key.

Architecture contract
─────────────────────
• Keys are loaded once at import time from Parameters.get_api_keys().
  To add more keys, set API_KEY, API_KEY_2, API_KEY_3, … as env vars.
• `_exhausted` is a per-session set of key indices that have returned
  quotaExceeded / rateLimitExceeded.  It resets on app restart or
  by calling reset_exhausted().
• `switch_to_next_key()` marks the *current* key as exhausted, then
  skips to the next non-exhausted index (wrapping around).  Raises
  RuntimeError when all keys are spent.
• Both sync and async callers can use this class — it is thread-safe
  only when accessed from a single thread per call (the YouTube API
  client is not thread-safe itself, so each QThread creates its own
  service object via `create_youtube_service()`).
• The `youtube_api_error_handler` decorator in youtube_error_handler.py
  handles both sync and async functions, catching HttpError, calling
  `switch_to_next_key()` on quota errors, and retrying up to
  `len(keys)` times.
"""
from __future__ import annotations

import logging
import os
from typing import Set

from app.config.stałe import Parameters

log = logging.getLogger(__name__)


class APIKeyManager:
    def __init__(self):
        self.keys = Parameters.get_api_keys()
        self.current_index = Parameters.get_active_api_key_index()
        self._exhausted: Set[int] = set()

    def get_current_key(self) -> str:
        return self.keys[self.current_index]

    def mark_exhausted(self):
        """Mark the current key as quota-exceeded for this session."""
        self._exhausted.add(self.current_index)
        log.info("Key #%d exhausted (%d/%d spent)",
                 self.current_index + 1, len(self._exhausted), len(self.keys))

    def has_available_keys(self) -> bool:
        """True if there is at least one key not yet exhausted."""
        return len(self._exhausted) < len(self.keys)

    def switch_to_next_key(self) -> str:
        """
        Move to the next non-exhausted key.
        Raises RuntimeError if all keys are spent.
        """
        self.mark_exhausted()

        if not self.has_available_keys():
            raise RuntimeError(
                "All YouTube API keys exhausted — quota exceeded on every key."
            )

        start = self.current_index
        while True:
            self.current_index = (self.current_index + 1) % len(self.keys)
            if self.current_index not in self._exhausted:
                break
            if self.current_index == start:
                raise RuntimeError("All YouTube API keys exhausted.")

        Parameters.set_active_api_key_index(self.current_index)
        log.info("Switched to key #%d", self.current_index + 1)
        return self.get_current_key()

    # legacy compat
    def has_more_keys(self) -> bool:
        return self.has_available_keys()

    def get_remaining_keys_count(self) -> int:
        return len(self.keys) - len(self._exhausted)

    @property
    def is_quota_exhausted(self) -> bool:
        """True when every configured key has been marked as quota-exceeded."""
        return len(self._exhausted) >= len(self.keys)

    def reset_exhausted(self):
        """Clear the exhausted set (manual reset or new session)."""
        self._exhausted.clear()
        log.info("Exhausted set cleared")


api_key_manager = APIKeyManager()
