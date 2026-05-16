from __future__ import annotations

import json
import logging
import re

import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted

from app.utils.gemini_key_manager import GeminiKeyManager

log = logging.getLogger(__name__)

_key_manager: GeminiKeyManager | None = None
_models: dict[str, genai.GenerativeModel] = {}


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


async def generate_json(prompt: str, *, temperature: float = 0.2) -> dict | list | None:
    manager = _get_key_manager()
    attempts = len(manager.keys)

    for _ in range(attempts):
        try:
            model = _get_model(temperature)
            res = await model.generate_content_async(prompt)
            raw = _strip_json_fences(res.text or "")
            return json.loads(raw)
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
