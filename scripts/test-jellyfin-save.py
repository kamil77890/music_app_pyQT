#!/usr/bin/env python3
"""Quick sanity check: save a dummy file to the Jellyfin library.

Tests both ``copy=True`` and ``copy=False`` modes and respects
``MUSIC_KEEP_LEGACY_COPY``.

Usage:
    sg media -c ".venv/bin/python scripts/test-jellyfin-save.py"
"""

import logging
import os
import sys
import tempfile

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s:%(message)s",
)

from app.config.jellyfin_config import JellyfinConfig
from app.logic.jellyfin_library import saveTrackToLibrary


def _cleanup_test_artifacts(*paths: str) -> None:
    for path in paths:
        try:
            if os.path.isfile(path):
                os.unlink(path)
                parent = os.path.dirname(path)
                if os.path.isdir(parent) and not os.listdir(parent):
                    os.rmdir(parent)
                    grandparent = os.path.dirname(parent)
                    if os.path.isdir(grandparent) and not os.listdir(grandparent):
                        os.rmdir(grandparent)
        except OSError:
            pass


def _temp_audio() -> str:
    fd, path = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)
    with open(path, "wb") as f:
        f.write(b"\xff\xfb\x90\x00" * 500)
    return path


def test_save(mode_name: str, copy_flag: bool) -> str | None:
    tmp_path = _temp_audio()
    print(f"\n--- Mode: {mode_name} (copy={copy_flag}) ---")
    print(f"    temp input: {tmp_path}")
    print(f"    temp exists: {os.path.isfile(tmp_path)}")

    try:
        return_path = saveTrackToLibrary(
            tmp_path,
            {
                "title": "Test Song",
                "artist": "Test Artist",
                "album": "Test Album",
                "trackNumber": "1",
                "year": "2024",
                "genre": "Test",
                "videoId": "test123",
                "sourceUrl": "https://youtube.com/watch?v=test123",
            },
            copy=copy_flag,
        )
        print(f"    Jellyfin path: {return_path}")
        print(f"    exists: {os.path.isfile(return_path)}")
        print(f"    size: {os.path.getsize(return_path)} bytes")
        print(f"    perms: {oct(os.stat(return_path).st_mode & 0o777)}")

        source_still_exists = os.path.isfile(tmp_path)
        print(f"    source after save: {'EXISTS' if source_still_exists else 'REMOVED'}")
        print(f"    (caller decides removal — saveTrackToLibrary never deletes source)")

        keep_legacy = JellyfinConfig.get_keep_legacy_copy()
        print(f"    MUSIC_KEEP_LEGACY_COPY: {keep_legacy}")

        return return_path
    except Exception as exc:
        print(f"    FAILED: {exc}", file=sys.stderr)
        return None
    finally:
        if os.path.isfile(tmp_path):
            os.unlink(tmp_path)


def main():
    print("=" * 60)
    print("Jellyfin library save test")
    print(f"LIBRARY: {JellyfinConfig.get_music_library_path()}")
    print(f"LEGACY: {JellyfinConfig.get_keep_legacy_copy()}")
    print(f"TEMP:   {JellyfinConfig.get_temp_dir()}")
    print(f"AUTO:   {JellyfinConfig.get_jellyfin_auto_scan()}")
    api_set = "yes" if JellyfinConfig.get_jellyfin_api_key() else "no"
    print(f"API:    {api_set}")
    if not JellyfinConfig.get_jellyfin_api_key():
        print("        → scan will be skipped (no key)")
    elif not JellyfinConfig.get_jellyfin_auto_scan():
        print("        → scan will be skipped (AUTO_SCAN=false)")
    else:
        print("        → scan will be triggered on save")
    print("=" * 60)

    paths: list[str | None] = []
    for mode, copy_flag in [("Copy (legacy)", True), ("Move (no legacy)", False)]:
        result = test_save(mode, copy_flag)
        paths.append(result)

    failed = [p for p in paths if p is None]

    # clean up only successful paths
    for p in paths:
        if p:
            _cleanup_test_artifacts(p)

    print(f"\n{'=' * 60}")
    if failed:
        print(f"RESULT: {len(failed)} TEST(S) FAILED")
        return 1
    print("RESULT: ALL TESTS PASSED")
    print(f"{'=' * 60}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
