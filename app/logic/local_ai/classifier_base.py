from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

CLASSIFIER_VERSION = "local-ai-v9-singles-album-collection"


def default_classification_result(*, metadata_source: str = "fallback", reason: str = "") -> dict[str, Any]:
    return {
        "genre": "Unknown Genre",
        "primary_genre": "Unknown Genre",
        "style": None,
        "subgenre": None,
        "collection": None,
        "mood": [],
        "tags": [],
        "metadata_quality": "low",
        "metadata_source": metadata_source,
        "classification_confidence": 0.0,
        "reason": reason,
    }


class LocalMetadataClassifier(ABC):
    @abstractmethod
    def classify(self, track: dict[str, Any]) -> dict[str, Any]:
        ...
