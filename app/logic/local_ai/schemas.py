from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EnrichedTrackMetadata:
    title: str
    artist: str
    album: str
    genre: str
    primary_genre: str = "Unknown Genre"
    style: str | None = None
    subgenre: str | None = None
    collection: str | None = None
    mood: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    metadata_quality: str = "low"
    metadata_source: str = "fallback"
    classification_confidence: float = 0.0
    reason: str = ""
    videoId: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "genre": self.genre,
            "primary_genre": self.primary_genre,
            "style": self.style,
            "subgenre": self.subgenre,
            "collection": self.collection,
            "mood": list(self.mood),
            "tags": list(self.tags),
            "metadata_quality": self.metadata_quality,
            "metadata_source": self.metadata_source,
            "classification_confidence": self.classification_confidence,
            "reason": self.reason,
            "videoId": self.videoId,
        }
