from __future__ import annotations

import json
import re
from typing import Any
from urllib import error, request

from app.logic.local_ai.classifier_base import LocalMetadataClassifier
from app.logic.local_ai.fallback_classifier import FallbackClassifier
from app.logic.local_ai.metadata_normalizer import (
    UNKNOWN_GENRE,
    calculate_metadata_quality,
    is_garbage_genre,
    normalize_album,
    normalize_artist,
    normalize_genre,
)

_CLASSIFICATION_PROMPT = """You classify music metadata.

Input:
title: {title}
artist: {artist}
album: {album}
existing_genre: {existing_genre}
source_title: {source_title}
description: {description}

Return strict JSON:
{{
  "genre": string,
  "primary_genre": string,
  "style": string|null,
  "subgenre": string|null,
  "mood": string[],
  "tags": string[],
  "metadata_quality": "low"|"medium"|"high",
  "classification_confidence": number,
  "reason": string
}}

Rules:
- Do not use YouTube IDs, hashes, URLs, filenames, or random IDs as genre.
- If unsure, use "Unknown Genre".
- Do not invent album names.
- Prefer broad, common music genres.
- Keep tags short and useful.
- Return only JSON.
"""


def _extract_json_object(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _clean_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned = []
    for item in value:
        text = str(item).strip()
        if text:
            cleaned.append(text)
    return cleaned


class OllamaClassifier(LocalMetadataClassifier):
    def __init__(self, *, base_url: str, model: str, timeout_seconds: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._fallback = FallbackClassifier()

    def classify(self, track: dict[str, Any]) -> dict[str, Any]:
        fallback = self._fallback.classify(track)
        prompt = _CLASSIFICATION_PROMPT.format(
            title=track.get("title") or "",
            artist=track.get("artist") or "",
            album=track.get("album") or "",
            existing_genre=track.get("genre") or "",
            source_title=track.get("source_title") or track.get("sourceTitle") or "",
            description=track.get("description") or "",
        )
        try:
            response_text = self._call_ollama(prompt)
            parsed = _extract_json_object(response_text)
            if not parsed:
                fallback["reason"] = "Local model returned invalid JSON."
                return fallback
            return self._merge_model_result(track, fallback, parsed)
        except Exception as exc:
            fallback["reason"] = f"Local model unavailable: {exc}"
            return fallback

    def _call_ollama(self, prompt: str) -> str:
        payload = json.dumps(
            {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "format": "json",
            }
        ).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise RuntimeError(str(exc.reason)) from exc

        message = body.get("message") if isinstance(body.get("message"), dict) else {}
        content = str(message.get("content") or "").strip()
        if content:
            return content

        # Some thinking models put JSON only in generate.thinking; keep a narrow fallback.
        thinking = str(body.get("thinking") or "").strip()
        return thinking

    def _merge_model_result(self, track: dict[str, Any], fallback: dict[str, Any], parsed: dict[str, Any]) -> dict[str, Any]:
        genre = normalize_genre(parsed.get("genre"))
        primary_genre = normalize_genre(parsed.get("primary_genre") or parsed.get("genre"))
        if genre == UNKNOWN_GENRE and primary_genre != UNKNOWN_GENRE:
            genre = primary_genre
        if primary_genre == UNKNOWN_GENRE and genre != UNKNOWN_GENRE:
            primary_genre = genre

        style = _clean_optional_text(parsed.get("style"))
        if style and is_garbage_genre(style):
            style = None
        subgenre = _clean_optional_text(parsed.get("subgenre"))
        if subgenre and is_garbage_genre(subgenre):
            subgenre = None

        mood = _clean_string_list(parsed.get("mood"))
        tags = _clean_string_list(parsed.get("tags"))
        metadata_quality = str(parsed.get("metadata_quality") or fallback.get("metadata_quality") or "low").lower()
        if metadata_quality not in {"low", "medium", "high"}:
            metadata_quality = fallback.get("metadata_quality", "low")

        try:
            confidence = float(parsed.get("classification_confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(round(confidence, 2), 1.0))

        reason = str(parsed.get("reason") or "Classified by local model.").strip()

        working = {
            "title": fallback["title"],
            "artist": fallback["artist"],
            "album": fallback["album"],
            "genre": genre,
        }

        return {
            "title": fallback["title"],
            "artist": fallback["artist"],
            "album": fallback["album"],
            "genre": genre,
            "primary_genre": primary_genre,
            "style": style,
            "subgenre": subgenre,
            "mood": mood,
            "tags": tags,
            "metadata_quality": metadata_quality if metadata_quality != "low" else calculate_metadata_quality(working),
            "metadata_source": "local_ai",
            "classification_confidence": confidence,
            "reason": reason,
            "videoId": fallback.get("videoId", ""),
        }
