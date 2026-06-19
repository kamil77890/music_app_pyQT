"""Metadata hygiene helpers.

This module intentionally contains only normalization and garbage detection.
Musical classification is handled by LocalMetadataClassifier adapters.
"""

from __future__ import annotations

from app.logic.local_ai.metadata_normalizer import UNKNOWN_GENRE, is_garbage_genre, normalize_genre

__all__ = ["UNKNOWN_GENRE", "is_garbage_genre", "normalize_genre"]
