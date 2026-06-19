from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return max(int(os.environ.get(name, str(default))), 0)
    except ValueError:
        return default


@dataclass(frozen=True)
class LocalAIConfig:
    metadata_enabled: bool = True
    provider: str = "ollama"
    ollama_url: str = "http://localhost:11434"
    model: str = "qwen2.5:3b"
    timeout_seconds: int = 60
    batch_size: int = 5
    cache_path: str = "data/local_ai_metadata_cache.json"


def get_config() -> LocalAIConfig:
    return LocalAIConfig(
        metadata_enabled=_env_bool("LOCAL_AI_METADATA_ENABLED", True),
        provider=os.environ.get("LOCAL_AI_PROVIDER", "ollama").strip().lower() or "ollama",
        ollama_url=os.environ.get("LOCAL_AI_OLLAMA_URL", "http://localhost:11434").strip() or "http://localhost:11434",
        model=os.environ.get("LOCAL_AI_MODEL", "qwen2.5:3b").strip(),
        timeout_seconds=_env_int("LOCAL_AI_TIMEOUT_SECONDS", 60) or 60,
        batch_size=_env_int("LOCAL_AI_BATCH_SIZE", 5) or 5,
        cache_path=os.environ.get("LOCAL_AI_CACHE_PATH", "data/local_ai_metadata_cache.json").strip() or "data/local_ai_metadata_cache.json",
    )
