import os
import logging

log = logging.getLogger(__name__)


class GeminiKeyManager:
    """
    Only handles GEMINI_* keys.
    No API_KEY_2 usage.
    """

    def __init__(self):
        self.keys = self._load_keys()
        self.index = 0

        if not self.keys:
            raise RuntimeError("No GEMINI_API_KEY configured")

    def _load_keys(self):
        keys = []

        primary = os.environ.get("GEMINI_API_KEY", "").strip()
        if primary:
            keys.append(primary)

        secondary = os.environ.get("GEMINI_API_KEY_2", "").strip()
        if secondary and secondary not in keys:
            keys.append(secondary)

        return keys

    def get_key(self):
        return self.keys[self.index]

    def rotate(self):
        self.index = (self.index + 1) % len(self.keys)
        log.warning(f"Rotated Gemini key → index {self.index}")