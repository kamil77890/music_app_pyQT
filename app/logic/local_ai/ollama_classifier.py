from __future__ import annotations

import json
import re
from typing import Any
from urllib import error, request

from app.logic.local_ai.classification_validator import validate_model_classification
from app.logic.local_ai.classifier_base import LocalMetadataClassifier
from app.logic.local_ai.fallback_classifier import FallbackClassifier
from app.logic.local_ai.metadata_normalizer import UNKNOWN_GENRE, calculate_metadata_quality, normalize_album, normalize_genre
from app.logic.local_ai.semantic_profile import build_semantic_profile

_CLASSIFICATION_PROMPT = """You classify music metadata for a local music library.

Input metadata:
title: {title}
artist: {artist}
album: {album}
existing_genre: {existing_genre}
source_title: {source_title}
description: {description}

Return strict JSON only. No markdown, no explanation outside JSON.

Required JSON shape:
{{
  "genre": string,
  "primary_genre": string,
  "style": string|null,
  "subgenre": string|null,
  "collection": string|null,
  "mood": string[],
  "tags": string[],
  "semantic_profile": {{
    "main_genre": string,
    "style_markers": string[],
    "context_markers": string[],
    "performance_type": string,
    "likely_group_theme": string
  }},
  "metadata_quality": "low"|"medium"|"high",
  "classification_confidence": number,
  "reason": string
}}

Core rules:
1. `genre` and `primary_genre` must be broad music genres only.
   Prefer one of:
   Rock, Pop, Electronic, Dance, Soundtrack, Classical, Hip Hop, Metal, Jazz, Folk, Ambient, Orchestral, Unknown Genre.

2. If unsure about the broad music genre, use "Unknown Genre".
   Do not force a genre just to fill the field.

3. Do not use context/media/franchise/platform labels as genre:
   Anime, Cyberpunk, Game, Movie, TV, YouTube, TikTok, OP, ED, Opening, Ending, Lyrics, Lyric Video.
   These may be tags, collection, or semantic_profile context markers when clearly supported by the input.

4. Do not use performance/style labels as genre:
   Piano, Nightcore, Cover, Remix, Instrumental, Acoustic, Orchestral Version.
   Put these in `style`, tags, and semantic_profile style_markers.

5. OST/opening/ending/media soundtrack tracks should usually use:
   primary_genre: Soundtrack
   genre: Soundtrack
   style: Piano/Orchestral/etc. only if clearly present.
   Do not infer Game/Movie/Anime unless explicitly supported by the input.

6. Nightcore:
   If title/source says Nightcore, set style to "Nightcore".
   If no clearer genre exists, prefer Electronic or Dance over Unknown Genre.
   Do not set genre to Nightcore.

7. Piano:
   If title/source says Piano Version, piano arrangement, piano cover, or similar, set style to "Piano".
   Do not set genre to Piano.

8. Rock Version:
   If title/source explicitly says Rock Version, use Rock as broad genre.
   Put Rock in tags. Do not use "Rock Version" as a tag.

9. Lyrics:
   If title/source says Lyrics or Lyric Video, add tag "Lyrics".
   Do not use Lyrics as genre, style, subgenre, or collection.

10. Tags must be short useful music/library labels.
    Good tags: Piano, Nightcore, Rock, Electronic, OST, Soundtrack, Lyrics, Instrumental, Cover, Remix, Dance, Jumpstyle, Ambient, Orchestral.
    Bad tags: song title words, artist names, random adjectives, "Young", "Harder", "Different", "Version", "Official", "HD", "Audio", "Video".

11. Do not put artist names, composer names, channel names, or song titles in tags.
    They already belong in artist/title fields.

12. `collection` is optional.
    Use it only for clear source/context labels from the input, such as Live for live tracks.
    If unsure, use null.

13. `subgenre` is optional.
    Use it only when it is a real music subgenre/style category.
    Do not put OP, ED, Lyrics, artist names, or song titles in subgenre.

14. `reason` must be short, factual, and cautious.
    Max 160 characters.
    Do not claim facts not present in the input.
    Avoid phrases like "clearly" unless the input explicitly proves it.

15. `classification_confidence`:
    0.90-1.00 only when title/metadata clearly states genre/style.
    0.60-0.85 when genre is likely but inferred.
    0.30-0.55 when only style/context is clear.
    0.00-0.25 when mostly unknown.

Semantic profile rules:
1. `likely_group_theme` is NOT the final album name. It is a short semantic grouping hint.
2. Examples: "nightcore electronic covers", "anime piano arrangements", "alternative rock", "pop rock", "classical piano".
3. Live tracks should keep the same likely_group_theme as similar non-live tracks when musically related.
4. Do not invent official album names.
5. Do not use Singles, Unknown Album, Misc, General, Music, Collection, or similar generic buckets.
6. Same input must always return the same JSON.
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
        base = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": "json",
        }
        option_sets: list[dict[str, Any] | None] = [
            {"temperature": 0, "top_p": 0.1, "seed": 42},
            {"temperature": 0, "top_p": 0.1},
            None,
        ]
        last_error: Exception | None = None
        for options in option_sets:
            payload_data = dict(base)
            if options is not None:
                payload_data["options"] = options
            try:
                return self._post_chat(payload_data)
            except RuntimeError as exc:
                last_error = exc
                message = str(exc).lower()
                if options is not None and "seed" in options and ("seed" in message or "unknown" in message):
                    continue
                raise
        if last_error is not None:
            raise last_error
        raise RuntimeError("Ollama chat request failed.")

    def _post_chat(self, payload_data: dict[str, Any]) -> str:
        payload = json.dumps(payload_data).encode("utf-8")
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

        semantic_profile = build_semantic_profile(
            track,
            genre=genre,
            style=validated["style"],
            tags=validated["tags"],
            model_profile=parsed.get("semantic_profile") if isinstance(parsed.get("semantic_profile"), dict) else None,
        )
        working = {
            "title": fallback["title"],
            "artist": fallback["artist"],
            "album": normalize_album(track.get("album")),
            "genre": genre,
        }
        metadata_quality = validated["metadata_quality"]
        if metadata_quality == "low":
            metadata_quality = calculate_metadata_quality(working)

        return {
            "title": fallback["title"],
            "artist": fallback["artist"],
            "album": working["album"],
            "album_kind": None,
            "album_source": "pending_grouping",
            "album_confidence": 0.0,
            "group_id": None,
            "genre": genre,
            "primary_genre": primary_genre,
            "style": validated["style"],
            "subgenre": validated["subgenre"],
            "collection": validated["collection"],
            "mood": validated["mood"],
            "tags": validated["tags"],
            "semantic_profile": semantic_profile,
            "metadata_quality": metadata_quality,
            "metadata_source": "local_ai",
            "classification_confidence": validated["classification_confidence"],
            "reason": validated["reason"],
            "videoId": fallback.get("videoId", ""),
        }
