from __future__ import annotations

from pathlib import Path

import pytest


def _configure_library(monkeypatch, tmp_path):
    from app.config.jellyfin_config import JellyfinConfig
    from app.logic import jellyfin_library

    library_root = tmp_path / "library"
    library_root.mkdir()
    source = tmp_path / "source.mp3"
    source.write_bytes(b"audio")

    monkeypatch.setattr(JellyfinConfig, "get_music_library_path", lambda: str(library_root))
    monkeypatch.setattr(JellyfinConfig, "get_output_format", lambda: "keep")
    monkeypatch.setattr(JellyfinConfig, "get_output_bitrate", lambda: "320k")
    monkeypatch.setattr(JellyfinConfig, "get_jellyfin_api_key", lambda: "")
    monkeypatch.setattr(JellyfinConfig, "get_music_library_owner", lambda: "")
    monkeypatch.setattr(JellyfinConfig, "get_music_library_group", lambda: "")
    monkeypatch.setattr(jellyfin_library, "_write_id3_tags", lambda *args, **kwargs: None)
    return jellyfin_library, library_root, source


def test_save_track_without_album_stages_in_incoming_artist_folder(monkeypatch, tmp_path):
    jellyfin_library, library_root, source = _configure_library(monkeypatch, tmp_path)

    final_path = jellyfin_library.saveTrackToLibrary(
        str(source),
        {"title": "Song", "artist": "Artist", "album": "", "trackNumber": "00"},
        copy=True,
    )

    expected = library_root / "_incoming" / "Artist" / "00 - Song.mp3"
    assert Path(final_path) == expected
    assert expected.exists()
    assert not (library_root / "Artist" / "Unknown Album").exists()


def test_save_track_unknown_album_sentinel_stages_in_incoming(monkeypatch, tmp_path):
    jellyfin_library, library_root, source = _configure_library(monkeypatch, tmp_path)

    final_path = jellyfin_library.saveTrackToLibrary(
        str(source),
        {"title": "Song", "artist": "Artist", "album": "Unknown Album", "trackNumber": "00"},
        copy=True,
    )

    assert Path(final_path) == library_root / "_incoming" / "Artist" / "00 - Song.mp3"
    assert not (library_root / "Artist" / "Unknown Album").exists()


def test_save_track_with_real_album_keeps_artist_album_path(monkeypatch, tmp_path):
    jellyfin_library, library_root, source = _configure_library(monkeypatch, tmp_path)

    final_path = jellyfin_library.saveTrackToLibrary(
        str(source),
        {"title": "Song", "artist": "Artist", "album": "Real Album", "trackNumber": "00"},
        copy=True,
    )

    assert Path(final_path) == library_root / "Artist" / "Real Album" / "00 - Song.mp3"


def test_incoming_duplicate_paths_get_suffix(monkeypatch, tmp_path):
    jellyfin_library, library_root, source = _configure_library(monkeypatch, tmp_path)
    existing = library_root / "_incoming" / "Artist" / "00 - Song.mp3"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"old")

    final_path = jellyfin_library.saveTrackToLibrary(
        str(source),
        {"title": "Song", "artist": "Artist", "album": "", "trackNumber": "00"},
        copy=True,
    )

    assert Path(final_path) == library_root / "_incoming" / "Artist" / "00 - Song (1).mp3"
    assert existing.read_bytes() == b"old"


def test_incoming_path_blocks_existing_symlink_escape(monkeypatch, tmp_path):
    jellyfin_library, library_root, source = _configure_library(monkeypatch, tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    incoming = library_root / "_incoming"
    incoming.mkdir()
    (incoming / "Artist").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="Path traversal blocked"):
        jellyfin_library.saveTrackToLibrary(
            str(source),
            {"title": "Song", "artist": "Artist", "album": "", "trackNumber": "00"},
            copy=True,
        )


def test_incoming_duplicate_resolution_skips_dangling_symlink(monkeypatch, tmp_path):
    jellyfin_library, library_root, source = _configure_library(monkeypatch, tmp_path)
    incoming_artist = library_root / "_incoming" / "Artist"
    incoming_artist.mkdir(parents=True)
    (incoming_artist / "00 - Song.mp3").write_bytes(b"old")
    outside_target = tmp_path / "outside" / "escaped.mp3"
    (incoming_artist / "00 - Song (1).mp3").symlink_to(outside_target)

    final_path = jellyfin_library.saveTrackToLibrary(
        str(source),
        {"title": "Song", "artist": "Artist", "album": "", "trackNumber": "00"},
        copy=True,
    )

    assert Path(final_path) == incoming_artist / "00 - Song (2).mp3"
    assert not outside_target.exists()


def test_incoming_existing_symlink_inside_library_gets_duplicate_suffix(monkeypatch, tmp_path):
    jellyfin_library, library_root, source = _configure_library(monkeypatch, tmp_path)
    incoming_artist = library_root / "_incoming" / "Artist"
    incoming_artist.mkdir(parents=True)
    redirected_target = library_root / "Other" / "escaped.mp3"
    redirected_target.parent.mkdir()
    (incoming_artist / "00 - Song.mp3").symlink_to(redirected_target)

    final_path = jellyfin_library.saveTrackToLibrary(
        str(source),
        {"title": "Song", "artist": "Artist", "album": "", "trackNumber": "00"},
        copy=True,
    )

    assert Path(final_path) == incoming_artist / "00 - Song (1).mp3"
    assert not redirected_target.exists()


def test_incoming_artist_directory_symlink_inside_library_is_blocked(monkeypatch, tmp_path):
    jellyfin_library, library_root, source = _configure_library(monkeypatch, tmp_path)
    redirected_dir = library_root / "Other"
    redirected_dir.mkdir()
    incoming = library_root / "_incoming"
    incoming.mkdir()
    (incoming / "Artist").symlink_to(redirected_dir, target_is_directory=True)

    with pytest.raises(ValueError, match="symlinked directory|Path traversal blocked"):
        jellyfin_library.saveTrackToLibrary(
            str(source),
            {"title": "Song", "artist": "Artist", "album": "", "trackNumber": "00"},
            copy=True,
        )

    assert not (redirected_dir / "00 - Song.mp3").exists()
