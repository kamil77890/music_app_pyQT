from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time

import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted

from app.utils.gemini_key_manager import GeminiKeyManager

log = logging.getLogger(__name__)

_key_manager: GeminiKeyManager | None = None
_models: dict[str, genai.GenerativeModel] = {}

# In-memory response cache to avoid re-spending tokens on identical prompts.
_GEMINI_CACHE_TTL = int(os.environ.get("GEMINI_CACHE_TTL_SECONDS", "21600"))  # 6h
_cache: dict[str, tuple[float, object]] = {}


def _cache_key(prompt: str, temperature: float) -> str:
    h = hashlib.sha256(f"{temperature}\n{prompt}".encode("utf-8")).hexdigest()
    return h


def _cache_get(key: str):
    entry = _cache.get(key)
    if not entry:
        return None
    ts, value = entry
    if time.time() - ts > _GEMINI_CACHE_TTL:
        _cache.pop(key, None)
        return None
    return value


def _cache_set(key: str, value: object) -> None:
    if value is None:
        return
    # Bound the cache to avoid unbounded growth.
    if len(_cache) > 256:
        _cache.clear()
    _cache[key] = (time.time(), value)


def _get_key_manager() -> GeminiKeyManager:
    global _key_manager
    if _key_manager is None:
        _key_manager = GeminiKeyManager()
    return _key_manager


def _get_model(temperature: float = 0.2) -> genai.GenerativeModel:
    key = _get_key_manager().get_key()
    if key not in _models:
        genai.configure(api_key=key)
        _models[key] = genai.GenerativeModel(
            model_name="gemini-2.5-flash-lite",
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=temperature,
            ),
        )
    return _models[key]


def _strip_json_fences(raw: str) -> str:
    raw = (raw or "").strip()
    raw = re.sub(r"^```[^\n]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)
    return raw.strip()


async def generate_json(
    prompt: str, *, temperature: float = 0.2, use_cache: bool = True
) -> dict | list | None:
    key = _cache_key(prompt, temperature)
    if use_cache:
        cached = _cache_get(key)
        if cached is not None:
            log.debug("Gemini cache hit")
            return cached

    manager = _get_key_manager()
    attempts = len(manager.keys)

    for _ in range(attempts):
        try:
            model = _get_model(temperature)
            res = await model.generate_content_async(prompt)
            raw = _strip_json_fences(res.text or "")
            parsed = json.loads(raw)
            if use_cache:
                _cache_set(key, parsed)
            return parsed
        except ResourceExhausted:
            log.warning("Gemini quota exceeded, rotating key")
            manager.rotate()
            _models.clear()
        except json.JSONDecodeError as e:
            log.warning("Gemini JSON parse error: %s", e)
            return None
        except Exception as e:
            log.warning("Gemini error: %s", e)
            return None
    return None
