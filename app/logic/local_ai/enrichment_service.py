from __future__ import annotations

import json
import os
import shutil
import threading
from pathlib import Path
from typing import Any

from app.config.jellyfin_config import JellyfinConfig
from app.logic.jellyfin_library import _resolve_duplicate, _safe_path, _set_permissions, sanitize_component
from app.logic.library_scanner import scan_music_files
from app.logic.local_ai.album_validator import is_missing_album
from app.logic.local_ai.classifier_base import CLASSIFIER_VERSION, LocalMetadataClassifier
from app.logic.local_ai.classification_validator import is_broad_genre, is_style_label
from app.logic.local_ai.config import LocalAIConfig, get_config
from app.logic.local_ai.fallback_classifier import FallbackClassifier
from app.logic.local_ai.metadata_normalizer import UNKNOWN_GENRE, normalize_album, normalize_genre
from app.logic.local_ai.ollama_availability import is_ollama_model_available
from app.logic.local_ai.ollama_classifier import OllamaClassifier

_cache_lock = threading.Lock()
_cache_state: dict[str, Any] = {"path": "", "data": {}}
_MANAGED_TAGS_ID3_DESC = "LOCAL_AI_TAGS"


def _parse_managed_tags(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    text = str(raw or "").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    except json.JSONDecodeError:
        pass
    return [part.strip() for part in text.split(",") if part.strip()]


def read_audio_file_metadata(path: str) -> dict[str, Any]:
    ext = os.path.splitext(path)[1].lower()
    out: dict[str, Any] = {"genre": "", "album": "", "managed_tags": []}
    if ext == ".mp3":
        from mutagen.id3 import ID3, ID3NoHeaderError

        try:
            id3 = ID3(path)
        except ID3NoHeaderError:
            return out
        if id3.get("TCON"):
            out["genre"] = str(id3["TCON"].text[0]).strip()
        if id3.get("TALB"):
            out["album"] = str(id3["TALB"].text[0]).strip()
        for key in id3.keys():
            if key.startswith("TXXX:") and key.split(":", 1)[1] == _MANAGED_TAGS_ID3_DESC:
                out["managed_tags"] = _parse_managed_tags(id3[key].text[0])
                break
    elif ext in (".m4a", ".mp4"):
        from mutagen.mp4 import MP4

        audio = MP4(path)
        if "\xa9gen" in audio:
            out["genre"] = str(audio["\xa9gen"][0]).strip()
        if "\xa9alb" in audio:
            out["album"] = str(audio["\xa9alb"][0]).strip()
        raw_tags = audio.get(f"----:com.apple.iTunes:{_MANAGED_TAGS_ID3_DESC}")
        if raw_tags:
            raw = raw_tags[0]
            text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
            out["managed_tags"] = _parse_managed_tags(text)
    return out


def _hydrate_track_from_file(track: dict[str, Any]) -> dict[str, Any]:
    path = track.get("path") or track.get("file_path") or ""
    if not path or not os.path.isfile(path):
        return dict(track)
    hydrated = dict(track)
    file_meta = read_audio_file_metadata(path)
    if file_meta.get("genre") and not hydrated.get("genre"):
        hydrated["genre"] = file_meta["genre"]
    if file_meta.get("album") and not hydrated.get("album"):
        hydrated["album"] = file_meta["album"]
    managed_tags = file_meta.get("managed_tags") or []
    if managed_tags:
        hydrated["file_tags"] = list(managed_tags)
    return hydrated


def _track_for_classification(track: dict[str, Any], *, repair_managed_albums: bool = False) -> dict[str, Any]:
    clean = dict(track)
    for key in ("tags", "file_tags", "managed_tags", "existing_tags"):
        clean.pop(key, None)
    if repair_managed_albums:
        clean["_repair_managed_albums"] = True
    return clean


def _writable_genre(metadata: dict[str, Any]) -> str:
    genre = normalize_genre(metadata.get("genre"))
    if genre == UNKNOWN_GENRE or is_style_label(genre) or not is_broad_genre(genre):
        return UNKNOWN_GENRE
    return genre


def _invalidate_cache_entry(cache: dict[str, Any], cache_key: str) -> None:
    cache.pop(cache_key, None)


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


def _load_cache_store_unlocked(cache_path: str) -> dict[str, Any]:
    if _cache_state["path"] != cache_path:
        _cache_state["path"] = cache_path
        _cache_state["data"] = _load_cache(cache_path)
    return _cache_state["data"]


def _get_cached_store(cache_path: str) -> dict[str, Any]:
    with _cache_lock:
        return _load_cache_store_unlocked(cache_path)


def _persist_cache_store_unlocked(cache_path: str, cache: dict[str, Any]) -> None:
    _save_cache(cache_path, cache)
    _cache_state["path"] = cache_path
    _cache_state["data"] = cache


def _persist_cache_store(cache_path: str, cache: dict[str, Any]) -> None:
    with _cache_lock:
        _persist_cache_store_unlocked(cache_path, cache)


def _strip_cache_meta(entry: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in entry.items() if k != "_cache_meta"}


def _cached_result_if_valid(
    cached: Any,
    *,
    track: dict[str, Any],
    config: LocalAIConfig,
) -> dict[str, Any] | None:
    if not isinstance(cached, dict):
        return None
    cache_meta = cached.get("_cache_meta")
    track_changed = not isinstance(cache_meta, dict) or cache_meta.get("track_hash") != _track_hash(track)
    if _cache_entry_complete(cached, config=config) and not track_changed:
        return _strip_cache_meta(cached)
    return None


def _cache_entry_complete(entry: Any, *, config: LocalAIConfig) -> bool:
    if not isinstance(entry, dict):
        return False
    required = {
        "genre",
        "primary_genre",
        "style",
        "subgenre",
        "collection",
        "mood",
        "tags",
        "album",
        "album_source",
        "album_confidence",
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
    effective_provider = config.provider if config.metadata_enabled else "fallback"
    effective_model = config.model if config.metadata_enabled else ""
    if cache_meta.get("model") != effective_model:
        return False
    if cache_meta.get("provider") != effective_provider:
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


def enrich_track_metadata(
    track: dict[str, Any],
    *,
    force_local_ai: bool = False,
    use_cache: bool = True,
    repair_managed_tags: bool = False,
    repair_managed_albums: bool = False,
) -> dict[str, Any]:
    config = get_config()
    hydrated = _hydrate_track_from_file(track)
    cache_key = _track_cache_key(hydrated)

    if repair_managed_tags or repair_managed_albums:
        use_cache = False
        with _cache_lock:
            cache = _load_cache_store_unlocked(config.cache_path)
            _invalidate_cache_entry(cache, cache_key)
            _persist_cache_store_unlocked(config.cache_path, cache)

    if use_cache:
        with _cache_lock:
            cache = _load_cache_store_unlocked(config.cache_path)
            cached_result = _cached_result_if_valid(cache.get(cache_key), track=hydrated, config=config)
            if cached_result is not None:
                return cached_result

    classifier = get_classifier(config=config, force_local_ai=force_local_ai)
    result = classifier.classify(_track_for_classification(hydrated, repair_managed_albums=repair_managed_albums))
    enriched = dict(hydrated)
    enriched.update(result)
    enriched.pop("file_tags", None)
    enriched.pop("_repair_managed_albums", None)

    if use_cache:
        with _cache_lock:
            cache = _load_cache_store_unlocked(config.cache_path)
            cached_result = _cached_result_if_valid(cache.get(cache_key), track=hydrated, config=config)
            if cached_result is not None:
                return cached_result
            cache[cache_key] = _attach_cache_meta(enriched, track=hydrated, config=config)
            _persist_cache_store_unlocked(config.cache_path, cache)

    return enriched


def write_audio_metadata(path: str, metadata: dict[str, Any], *, write_album: bool = True, write_tags: bool = True) -> None:
    ext = os.path.splitext(path)[1].lower()
    genre = _writable_genre(metadata) if write_tags else UNKNOWN_GENRE
    video_id = metadata.get("videoId") or metadata.get("video_id") or ""
    managed_tags = [str(tag).strip() for tag in (metadata.get("tags") or []) if str(tag).strip()]
    managed_tags_payload = json.dumps(managed_tags, ensure_ascii=False)
    album = normalize_album(metadata.get("album")) if write_album else UNKNOWN_ALBUM
    if ext == ".mp3":
        from mutagen.id3 import ID3, ID3NoHeaderError, TALB, TCON, TXXX

        try:
            id3 = ID3(path)
        except ID3NoHeaderError:
            id3 = ID3()
        if write_tags:
            id3.delall("TCON")
            if genre != UNKNOWN_GENRE:
                id3.add(TCON(encoding=3, text=genre))
            id3.delall(f"TXXX:{_MANAGED_TAGS_ID3_DESC}")
            if managed_tags:
                id3.add(TXXX(encoding=3, desc=_MANAGED_TAGS_ID3_DESC, text=managed_tags_payload))
        if write_album and not is_missing_album(album):
            id3.delall("TALB")
            id3.add(TALB(encoding=3, text=album))
        if video_id:
            id3.delall("TXXX:YOUTUBE_VIDEO_ID")
            id3.add(TXXX(encoding=3, desc="YOUTUBE_VIDEO_ID", text=video_id))
        id3.save(path, v2_version=3, v1=2)
    elif ext in (".m4a", ".mp4"):
        from mutagen.mp4 import MP4

        audio = MP4(path)
        if write_tags:
            if genre != UNKNOWN_GENRE:
                audio["\xa9gen"] = [genre]
            elif "\xa9gen" in audio:
                del audio["\xa9gen"]
            managed_key = f"----:com.apple.iTunes:{_MANAGED_TAGS_ID3_DESC}"
            if managed_key in audio:
                del audio[managed_key]
            if managed_tags:
                audio[managed_key] = [managed_tags_payload.encode("utf-8")]
        if write_album and not is_missing_album(album):
            audio["\xa9alb"] = [album]
        if video_id:
            audio["----:com.apple.iTunes:YOUTUBE_VIDEO_ID"] = [video_id.encode("utf-8")]
        audio.save()


def plan_track_album_move(
    *,
    path: str,
    artist: str,
    target_album: str,
    music_dir: str,
) -> dict[str, str] | None:
    if not path or not os.path.isfile(path):
        return None
    if is_missing_album(target_album):
        return None

    source = Path(os.path.realpath(path))
    lib_root = Path(os.path.realpath(music_dir))
    if not str(source).startswith(str(lib_root) + os.sep):
        return None

    current_album_dir = source.parent
    if sanitize_component(current_album_dir.name) != sanitize_component("Unknown Album"):
        return None

    filename = source.name
    destination = _safe_path(music_dir, artist, target_album, filename)
    destination = _resolve_duplicate(destination)
    if destination == source:
        return None
    return {
        "from": str(source),
        "to": str(destination),
        "artist": artist,
        "album": target_album,
    }


def move_track_to_album_folder(
    *,
    path: str,
    artist: str,
    target_album: str,
    music_dir: str,
    dry_run: bool = False,
) -> dict[str, str] | None:
    plan = plan_track_album_move(path=path, artist=artist, target_album=target_album, music_dir=music_dir)
    if not plan:
        return None
    if dry_run:
        return plan

    source = Path(plan["from"])
    destination = Path(plan["to"])
    destination.parent.mkdir(parents=True, exist_ok=True)
    _set_permissions(destination.parent)
    shutil.move(str(source), str(destination))
    _set_permissions(destination)

    old_album_dir = source.parent
    if old_album_dir.name == "Unknown Album" and old_album_dir.is_dir() and not any(old_album_dir.iterdir()):
        try:
            old_album_dir.rmdir()
        except OSError:
            pass
    plan["moved"] = "true"
    return plan


def enrich_library_batch(
    *,
    music_dir: str | None = None,
    limit: int | None = None,
    only_missing_genre: bool = False,
    only_low_quality: bool = False,
    dry_run: bool = True,
    write_tags: bool = False,
    write_albums: bool = False,
    move_files: bool = False,
    group_preview: bool = False,
    force_local_ai: bool = False,
    repair_managed_tags: bool = False,
    repair_managed_albums: bool = False,
) -> dict[str, Any]:
    config = get_config()
    cache = _load_cache(config.cache_path)
    lib_dir = music_dir or JellyfinConfig.get_music_library_path()
    songs = scan_music_files(lib_dir)
    summary = {
        "analyzed": 0,
        "genres_updated": 0,
        "albums_updated": 0,
        "tags_updated": 0,
        "files_moved": 0,
        "move_plans": [],
        "errors": 0,
        "dry_run": dry_run,
        "write_tags": write_tags,
        "write_albums": write_albums,
        "move_files": move_files,
    }
    groups: dict[str, int] = {}
    subgenres: dict[str, int] = {}
    processed = 0
    needs_repair = repair_managed_tags or repair_managed_albums

    for song in songs:
        if limit is not None and processed >= limit:
            break
        try:
            cache_key = _track_cache_key(song)
            cached = cache.get(cache_key)
            cache_meta = cached.get("_cache_meta") if isinstance(cached, dict) else None
            track_changed = not isinstance(cache_meta, dict) or cache_meta.get("track_hash") != _track_hash(song)
            if _cache_entry_complete(cached, config=config) and not track_changed and not needs_repair:
                enriched = {k: v for k, v in cached.items() if k != "_cache_meta"}
            else:
                enriched = enrich_track_metadata(
                    song,
                    force_local_ai=force_local_ai,
                    repair_managed_tags=repair_managed_tags,
                    repair_managed_albums=repair_managed_albums,
                )
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
            if song.get("path") and (write_tags or write_albums) and not dry_run:
                write_audio_metadata(
                    song["path"],
                    enriched,
                    write_album=write_albums,
                    write_tags=write_tags,
                )
            if move_files and song.get("path"):
                move_result = move_track_to_album_folder(
                    path=song["path"],
                    artist=str(enriched.get("artist") or song.get("artist") or "Unknown Artist"),
                    target_album=str(enriched.get("album") or ""),
                    music_dir=lib_dir,
                    dry_run=dry_run,
                )
                if move_result:
                    summary["move_plans"].append(move_result)
                    if not dry_run and move_result.get("moved") == "true":
                        summary["files_moved"] += 1
                        enriched["path"] = move_result["to"]
                        cache[_track_cache_key(enriched)] = _attach_cache_meta(enriched, track=enriched, config=config)
        except Exception:
            summary["errors"] += 1

    _save_cache(config.cache_path, cache)
    if group_preview:
        summary["groups"] = groups
        summary["subgenres"] = subgenres
    return summary
