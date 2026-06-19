from __future__ import annotations

import json
from typing import Any
from urllib import error, request


def list_ollama_models(base_url: str, *, timeout_seconds: int = 5) -> list[str]:
    req = request.Request(f"{base_url.rstrip('/')}/api/tags", method="GET")
    try:
        with request.urlopen(req, timeout=timeout_seconds) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (error.HTTPError, error.URLError, TimeoutError, json.JSONDecodeError):
        return []
    models = payload.get("models") if isinstance(payload, dict) else []
    if not isinstance(models, list):
        return []
    names = []
    for item in models:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            if name:
                names.append(name)
    return names


def is_ollama_model_available(base_url: str, model: str, *, timeout_seconds: int = 5) -> bool:
    model = model.strip()
    if not model:
        return False
    installed = list_ollama_models(base_url, timeout_seconds=timeout_seconds)
    if model in installed:
        return True
    model_base = model.split(":", 1)[0]
    return any(name.split(":", 1)[0] == model_base for name in installed)


def is_ollama_reachable(base_url: str, *, timeout_seconds: int = 5) -> bool:
    return bool(list_ollama_models(base_url, timeout_seconds=timeout_seconds) or _ping_ollama(base_url, timeout_seconds=timeout_seconds))


def _ping_ollama(base_url: str, *, timeout_seconds: int = 5) -> bool:
    req = request.Request(f"{base_url.rstrip('/')}/api/tags", method="GET")
    try:
        with request.urlopen(req, timeout=timeout_seconds):
            return True
    except (error.HTTPError, error.URLError, TimeoutError):
        return False
