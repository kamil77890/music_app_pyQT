from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.config.jellyfin_config import JellyfinConfig
from app.logic.library_scanner import scan_music_files
from app.logic.local_ai.classifier_base import CLASSIFIER_VERSION, LocalMetadataClassifier
from app.logic.local_ai.config import LocalAIConfig, get_config
from app.logic.local_ai.fallback_classifier import FallbackClassifier
from app.logic.local_ai.metadata_normalizer import UNKNOWN_GENRE, normalize_album, normalize_genre
from app.logic.local_ai.ollama_availability import is_ollama_model_available
from app.logic.local_ai.ollama_classifier import OllamaClassifier


def _track_cache_key(track: dict[str, Any]) -> str:
    path = track.get("path") or track.get("file_path") or ""
    mtime = track.get("fileMtime") or ""
    size = track.get("fileSize") or ""
    return f"{path}|{mtime}|{size}"


def _track_hash(track: dict[str, Any]) -> str:
    parts = [
        track.get("path") or track.get("file_path") or "",
        track.get("fileMtime") or "",
        track.get("fileSize") or "",
        track.get("title") or "",
        track.get("artist") or "",
        track.get("album") or "",
    ]
    return "|".join(str(part) for part in parts)


def _load_cache(cache_path: str) -> dict[str, Any]:
    path = Path(cache_path)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_cache(cache_path: str, cache: dict[str, Any]) -> None:
    path = Path(cache_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _cache_entry_complete(entry: Any, *, config: LocalAIConfig) -> bool:
    if not isinstance(entry, dict):
        return False
    required = {
        "genre",
        "primary_genre",
        "style",
        "subgenre",
        "mood",
        "tags",
        "metadata_quality",
        "metadata_source",
        "classification_confidence",
        "reason",
    }
    if not required.issubset(entry.keys()):
        return False
    cache_meta = entry.get("_cache_meta")
    if not isinstance(cache_meta, dict):
        return False
    if cache_meta.get("classifier_version") != CLASSIFIER_VERSION:
        return False
    if cache_meta.get("model") != config.model:
        return False
    if cache_meta.get("provider") != config.provider:
        return False
    if cache_meta.get("metadata_enabled") != config.metadata_enabled:
        return False
    return True


def get_classifier(*, config: LocalAIConfig | None = None, force_local_ai: bool = False) -> LocalMetadataClassifier:
    config = config or get_config()
    use_local_ai = force_local_ai or config.metadata_enabled
    if use_local_ai and config.provider == "ollama" and config.model:
        if is_ollama_model_available(config.ollama_url, config.model, timeout_seconds=min(config.timeout_seconds, 10)):
            return OllamaClassifier(
                base_url=config.ollama_url,
                model=config.model,
                timeout_seconds=config.timeout_seconds,
            )
    return FallbackClassifier()


def _attach_cache_meta(result: dict[str, Any], *, track: dict[str, Any], config: LocalAIConfig) -> dict[str, Any]:
    enriched = dict(result)
    enriched["_cache_meta"] = {
        "classifier_version": CLASSIFIER_VERSION,
        "provider": config.provider if config.metadata_enabled else "fallback",
        "model": config.model if config.metadata_enabled else "",
        "metadata_enabled": config.metadata_enabled,
        "track_hash": _track_hash(track),
    }
    return enriched


def enrich_track_metadata(track: dict[str, Any], *, force_local_ai: bool = False, use_cache: bool = True) -> dict[str, Any]:
    config = get_config()
    cache_key = _track_cache_key(track)
    cache: dict[str, Any] | None = None

    if use_cache:
        cache = _load_cache(config.cache_path)
        cached = cache.get(cache_key)
        cache_meta = cached.get("_cache_meta") if isinstance(cached, dict) else None
        track_changed = not isinstance(cache_meta, dict) or cache_meta.get("track_hash") != _track_hash(track)
        if _cache_entry_complete(cached, config=config) and not track_changed:
            return {k: v for k, v in cached.items() if k != "_cache_meta"}

    classifier = get_classifier(config=config, force_local_ai=force_local_ai)
    result = classifier.classify(track)
    enriched = dict(track)
    enriched.update(result)

    if use_cache:
        if cache is None:
            cache = _load_cache(config.cache_path)
        cache[cache_key] = _attach_cache_meta(enriched, track=track, config=config)
        _save_cache(config.cache_path, cache)

    return enriched


def write_audio_metadata(path: str, metadata: dict[str, Any]) -> None:
    ext = os.path.splitext(path)[1].lower()
    genre = normalize_genre(metadata.get("genre"))
    video_id = metadata.get("videoId") or metadata.get("video_id") or ""
    if ext == ".mp3":
        from mutagen.id3 import ID3, ID3NoHeaderError, TCON, TXXX

        try:
            id3 = ID3(path)
        except ID3NoHeaderError:
            id3 = ID3()
        id3.delall("TCON")
        if genre != UNKNOWN_GENRE:
            id3.add(TCON(encoding=3, text=genre))
        if video_id:
            id3.delall("TXXX:YOUTUBE_VIDEO_ID")
            id3.add(TXXX(encoding=3, desc="YOUTUBE_VIDEO_ID", text=video_id))
        id3.save(path, v2_version=3, v1=2)
    elif ext in (".m4a", ".mp4"):
        from mutagen.mp4 import MP4

        audio = MP4(path)
        if genre != UNKNOWN_GENRE:
            audio["\xa9gen"] = [genre]
        elif "\xa9gen" in audio:
            del audio["\xa9gen"]
        if video_id:
            audio["----:com.apple.iTunes:YOUTUBE_VIDEO_ID"] = [video_id.encode("utf-8")]
        audio.save()


def enrich_library_batch(
    *,
    music_dir: str | None = None,
    limit: int | None = None,
    only_missing_genre: bool = False,
    only_low_quality: bool = False,
    dry_run: bool = True,
    write_tags: bool = False,
    group_preview: bool = False,
    force_local_ai: bool = False,
) -> dict[str, Any]:
    config = get_config()
    cache = _load_cache(config.cache_path)
    songs = scan_music_files(music_dir or JellyfinConfig.get_music_library_path())
    summary = {"analyzed": 0, "genres_updated": 0, "albums_updated": 0, "tags_updated": 0, "errors": 0, "dry_run": dry_run, "write_tags": write_tags}
    groups: dict[str, int] = {}
    subgenres: dict[str, int] = {}
    processed = 0

    for song in songs:
        if limit is not None and processed >= limit:
            break
        try:
            cache_key = _track_cache_key(song)
            cached = cache.get(cache_key)
            cache_meta = cached.get("_cache_meta") if isinstance(cached, dict) else None
            track_changed = not isinstance(cache_meta, dict) or cache_meta.get("track_hash") != _track_hash(song)
            if _cache_entry_complete(cached, config=config) and not track_changed:
                enriched = {k: v for k, v in cached.items() if k != "_cache_meta"}
            else:
                enriched = enrich_track_metadata(song, force_local_ai=force_local_ai)
            if only_missing_genre and normalize_genre(song.get("genre")) != UNKNOWN_GENRE:
                continue
            if only_low_quality and enriched.get("metadata_quality") != "low":
                continue
            processed += 1
            summary["analyzed"] += 1
            if enriched.get("genre") != normalize_genre(song.get("genre")):
                summary["genres_updated"] += 1
            if enriched.get("album") != normalize_album(song.get("album")):
                summary["albums_updated"] += 1
            if enriched.get("tags") != (song.get("tags") or []):
                summary["tags_updated"] += 1
            if group_preview:
                group = enriched.get("style") or enriched.get("primary_genre") or "Unknown"
                groups[group] = groups.get(group, 0) + 1
                sub = enriched.get("subgenre")
                if sub:
                    subgenres[sub] = subgenres.get(sub, 0) + 1
            cache[cache_key] = _attach_cache_meta(enriched, track=song, config=config)
            if write_tags and not dry_run and song.get("path"):
                write_audio_metadata(song["path"], enriched)
        except Exception:
            summary["errors"] += 1

    _save_cache(config.cache_path, cache)
    if group_preview:
        summary["groups"] = groups
        summary["subgenres"] = subgenres
    return summary
