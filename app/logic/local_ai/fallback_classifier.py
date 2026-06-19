from __future__ import annotations

from pathlib import Path
from typing import Any

from app.logic.local_ai.album_validator import resolve_track_album
from app.logic.local_ai.classifier_base import LocalMetadataClassifier
from app.logic.local_ai.metadata_normalizer import (
    UNKNOWN_GENRE,
    calculate_metadata_quality,
    is_garbage_genre,
    normalize_album,
    normalize_artist,
    normalize_genre,
)


class FallbackClassifier(LocalMetadataClassifier):
    """Safe metadata hygiene without musical guessing."""

    def classify(self, track: dict[str, Any]) -> dict[str, Any]:
        title = str(track.get("title") or Path(str(track.get("path") or "Unknown")).stem or "Unknown").strip()
        artist = normalize_artist(track.get("artist"))
        album = normalize_album(track.get("album"))
        raw_genre = track.get("genre") or track.get("id3_genre") or ""
        clean_genre = normalize_genre(raw_genre)
        primary_genre = clean_genre if clean_genre != UNKNOWN_GENRE else UNKNOWN_GENRE

        confidence = 0.2 if clean_genre != UNKNOWN_GENRE else 0.0
        reason = "Existing genre preserved after metadata cleanup." if clean_genre != UNKNOWN_GENRE else "No reliable genre metadata available."

        working = {
            "title": title,
            "artist": artist,
            "album": album,
            "genre": clean_genre,
        }

        final_album, album_source, album_confidence = resolve_track_album(
            track=track,
            genre=clean_genre,
            repair_managed_albums=bool(track.get("_repair_managed_albums")),
        )
        working["album"] = final_album

        return {
            "title": title,
            "artist": artist,
            "album": final_album,
            "album_source": album_source,
            "album_confidence": album_confidence,
            "genre": clean_genre,
            "primary_genre": primary_genre,
            "style": None,
            "subgenre": None,
            "collection": None,
            "mood": [],
            "tags": [],
            "metadata_quality": calculate_metadata_quality(working),
            "metadata_source": "fallback",
            "classification_confidence": confidence,
            "reason": reason,
            "videoId": _extract_video_id(track, raw_genre),
        }


def _extract_video_id(track: dict[str, Any], raw_genre: str) -> str:
    video_id = track.get("videoId") or track.get("video_id") or ""
    if not video_id and is_garbage_genre(raw_genre):
        raw = str(raw_genre or "").strip()
        if len(raw) == 11 and all(ch.isalnum() or ch in "_-" for ch in raw):
            return raw
    return str(video_id or "")
