from __future__ import annotations

import json
import re
from typing import Any
from urllib import error, request

from app.logic.local_ai.classification_validator import validate_model_classification
from app.logic.local_ai.classifier_base import LocalMetadataClassifier
from app.logic.local_ai.fallback_classifier import FallbackClassifier
from app.logic.local_ai.metadata_normalizer import UNKNOWN_GENRE, calculate_metadata_quality, normalize_genre

_CLASSIFICATION_PROMPT = """You classify music metadata.

Input:
title: {title}
artist: {artist}
album: {album}
existing_genre: {existing_genre}
source_title: {source_title}
description: {description}

Return strict JSON only. No markdown.
{{
  "genre": string,
  "primary_genre": string,
  "style": string|null,
  "subgenre": string|null,
  "collection": string|null,
  "mood": string[],
  "tags": string[],
  "metadata_quality": "low"|"medium"|"high",
  "classification_confidence": number,
  "reason": string
}}

Rules:
1. genre and primary_genre must be broad music genres only.
   Valid examples: Rock, Pop, Electronic, Soundtrack, Classical, Hip Hop, Metal, Jazz, Folk, Ambient, Dance, Unknown Genre.

2. Do not use franchise/media/context labels as genre:
   Anime, Cyberpunk, Game, Movie, YouTube, TikTok, OP, ED, Lyrics.
   Put these into collection or tags instead.

3. Do not use performance/style labels as primary genre unless they are commonly used as genre.
   Piano, Cover, Remix, Nightcore, Instrumental should usually go to style and/or tags.

4. OST/opening/ending/anime/movie/game music should usually use:
   primary_genre: Soundtrack
   collection/tags: Anime, Game, Movie, OST, Opening, Ending, etc.

5. If the title says Piano Version or piano arrangement:
   style should include Piano.
   Do not set genre to Piano.

6. If the title says Nightcore:
   style should include Nightcore.
   Choose primary_genre by musical context if clear, otherwise Electronic or Unknown Genre.

7. Do not use YouTube IDs, hashes, URLs, filenames, or random IDs as genre.
8. If unsure, use "Unknown Genre".
9. Do not invent album names.
10. Keep tags short and useful.
11. Keep reason short, factual, and based only on the provided metadata.
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

        thinking = str(body.get("thinking") or "").strip()
        return thinking

    def _merge_model_result(self, track: dict[str, Any], fallback: dict[str, Any], parsed: dict[str, Any]) -> dict[str, Any]:
        validated = validate_model_classification(parsed, track=track)

        genre = validated["genre"]
        primary_genre = validated["primary_genre"]
        if genre == UNKNOWN_GENRE and primary_genre != UNKNOWN_GENRE:
            genre = primary_genre
        if primary_genre == UNKNOWN_GENRE and genre != UNKNOWN_GENRE:
            primary_genre = genre

        working = {
            "title": fallback["title"],
            "artist": fallback["artist"],
            "album": fallback["album"],
            "genre": genre,
        }
        metadata_quality = validated["metadata_quality"]
        if metadata_quality == "low":
            metadata_quality = calculate_metadata_quality(working)

        return {
            "title": fallback["title"],
            "artist": fallback["artist"],
            "album": fallback["album"],
            "genre": genre,
            "primary_genre": primary_genre,
            "style": validated["style"],
            "subgenre": validated["subgenre"],
            "collection": validated["collection"],
            "mood": validated["mood"],
            "tags": validated["tags"],
            "metadata_quality": metadata_quality,
            "metadata_source": "local_ai",
            "classification_confidence": validated["classification_confidence"],
            "reason": validated["reason"],
            "videoId": fallback.get("videoId", ""),
        }
