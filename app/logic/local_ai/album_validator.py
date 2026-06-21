from __future__ import annotations

from app.logic.local_ai.album_group_validator import (
    LEGACY_MANAGED_ALBUM_FOLDERS,
    is_legacy_managed_album_folder,
    is_missing_album,
    is_official_or_existing_album,
    is_repairable_source_album_folder,
    is_weak_group_name,
    sanitize_group_name,
    validate_group_name,
)

FAKE_CATEGORY_ALBUM_FOLDERS = LEGACY_MANAGED_ALBUM_FOLDERS


def sanitize_album_name(value):  # noqa: ANN001
    return sanitize_group_name(value)


def is_fake_category_album(value):  # noqa: ANN001
    return is_legacy_managed_album_folder(value)


def is_real_album(value, *, track=None):  # noqa: ANN001
    return is_official_or_existing_album(value, track=track)
