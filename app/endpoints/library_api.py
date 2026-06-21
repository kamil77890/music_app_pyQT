import logging
import os
import re
from collections import defaultdict

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, FileResponse

from app.config.jellyfin_config import JellyfinConfig
from app.endpoints.api_errors import api_error
from app.logic.library_scanner import scan_music_files
from app.logic.local_ai.album_group_registry import load_registry, registry_group_for_track
from app.logic.local_ai.config import get_config
from app.logic.local_ai.enrichment_service import enrich_track_metadata, read_library_layout_metadata, _load_cache, _track_cache_key
from app.logic.ultimate_downloader import download_song, extract_video_id

_YT_VIDEO_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{11}$")

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["library-api"])


def _download_error_code(exc: HTTPException) -> str:
    header_code = (exc.headers or {}).get("X-Error-Code")
    if header_code:
        return header_code
    detail = str(exc.detail or "")
    if "403" in detail or "blocked" in detail or "Forbidden" in detail:
        return "YTDLP_FORBIDDEN"
    if "429" in detail or "rate-limit" in detail or "Too Many Requests" in detail:
        return "YTDLP_RATE_LIMITED"
    if exc.status_code == 422 or "without an audio file" in detail or "file not created" in detail:
        return "NO_OUTPUT_FILE"
    return "INTERNAL_ERROR"


def _sort_text(value: str) -> tuple[str, str]:
    return (value.lower(), value)


def _group_from_saved_entry(entry: dict | None) -> str:
    if not isinstance(entry, dict):
        return ""
    for key in ("library_group", "managed_library_group", "LOCAL_AI_LIBRARY_GROUP", "group_name"):
        value = str(entry.get(key) or "").strip()
        if value:
            return value
    return ""


def _saved_library_group(song: dict, *, cache: dict | None = None, registry: dict | None = None) -> str:
    for key in ("library_group", "managed_library_group"):
        value = str(song.get(key) or "").strip()
        if value:
            return value

    cache_group = _group_from_saved_entry((cache or {}).get(_track_cache_key(song)))
    if cache_group:
        return cache_group

    registry_group = registry_group_for_track(registry or {}, _track_cache_key(song))
    registry_value = _group_from_saved_entry(registry_group)
    if registry_value:
        return registry_value

    path = str(song.get("path") or "")
    if path and os.path.isfile(path):
        file_meta = read_library_layout_metadata(path)
        value = str(file_meta.get("library_group") or "").strip()
        if value:
            return value

    lib_path = JellyfinConfig.get_music_library_path()
    norm_lib = os.path.normpath(os.path.realpath(lib_path))
    norm_path = os.path.normpath(os.path.realpath(path)) if path else ""
    if norm_path and os.path.commonpath([norm_lib, norm_path]) == norm_lib:
        rel = os.path.relpath(norm_path, norm_lib).split(os.sep)
        if rel and rel[0] and rel[0] != "_incoming":
            return rel[0]
    return "Ungrouped"


def build_library_groups_response(songs: list[dict]) -> dict:
    grouped: dict[str, dict[str, dict]] = defaultdict(dict)
    covers: dict[str, str] = {}
    config = get_config()
    cache = _load_cache(config.cache_path)
    registry = load_registry(config.album_groups_registry_path)
    for song in songs:
        group = _saved_library_group(song, cache=cache, registry=registry)
        artist = str(song.get("artist") or "Unknown Artist").strip() or "Unknown Artist"
        artist_node = grouped[group].setdefault(artist, {"name": artist, "track_count": 0, "tracks": []})
        artist_node["track_count"] += 1
        artist_node["tracks"].append(song)
        if group not in covers and song.get("cover"):
            covers[group] = str(song["cover"])

    groups = []
    for group_name in sorted(grouped, key=_sort_text):
        artists = []
        for artist_name in sorted(grouped[group_name], key=_sort_text):
            node = grouped[group_name][artist_name]
            node["tracks"] = sorted(
                node["tracks"],
                key=lambda item: (
                    str(item.get("title") or "").lower(),
                    str(item.get("title") or ""),
                    str(item.get("path") or ""),
                ),
            )
            artists.append(node)
        groups.append({"name": group_name, "cover": covers.get(group_name, ""), "artists": artists})
    return {"groups": groups}


@router.get("/health")
async def health():
    return {"ok": True, "service": "music_app_pyQT", "library": JellyfinConfig.get_music_library_path()}


@router.post("/download-library")
async def download_to_library(body: dict = Body(...)):
    url = (body.get("url") or "").strip()
    if not url:
        return api_error("MISSING_FIELD", "Missing 'url' field.", 400)

    candidate_id = extract_video_id(url)
    if not _YT_VIDEO_ID_RE.match(candidate_id):
        return api_error("INVALID_URL", "This is not a valid YouTube URL.", 400)
    video_id = candidate_id

    try:
        result = await run_in_threadpool(download_song, video_id)
        jellyfin_path = result.get("jellyfin_path", "")
        meta = {}
        if jellyfin_path:
            ext = os.path.splitext(jellyfin_path)[1].lstrip(".").lower()
            if ext in ("mp3", "mp4", "m4a"):
                from app.logic.metadata.add_metadata import verify_metadata
                try:
                    meta = verify_metadata(jellyfin_path, ext)
                except Exception as meta_err:
                    log.warning("verify_metadata failed for %s: %s", jellyfin_path, meta_err)
        return {
            "ok": True,
            "status": "saved",
            "title": meta.get("title") or os.path.splitext(os.path.basename(jellyfin_path))[0],
            "artist": meta.get("artist") or "Unknown Artist",
            "album": meta.get("album") or "Unknown Album",
            "jellyfin_path": jellyfin_path,
            "videoId": video_id,
        }
    except HTTPException as exc:
        error_code = _download_error_code(exc)
        message = str(exc.detail) if exc.detail else "Request failed."
        return api_error(error_code, message, exc.status_code, detail=message)
    except Exception as exc:
        log.warning("download-library failed for %s: %s", video_id, exc)
        return api_error("INTERNAL_ERROR", str(exc), 500)


@router.get("/library/songs")
async def library_songs(
    q: str = Query(default=""),
    limit: int = Query(default=200, ge=1, le=1000),
):
    lib_path = JellyfinConfig.get_music_library_path()
    if not os.path.isdir(lib_path):
        return {"songs": [], "total": 0, "library_path": lib_path}

    scanned = scan_music_files(lib_path)
    scanned.sort(key=lambda s: s.get("title", "").lower())

    if q:
        ql = q.lower()
        scanned = [
            s for s in scanned
            if ql in s.get("title", "").lower()
            or ql in s.get("artist", "").lower()
            or ql in s.get("album", "").lower()
        ]

    total = len(scanned)
    songs = [enrich_track_metadata(song) for song in scanned[:limit]]

    return {
        "songs": songs,
        "total": total,
        "library_path": lib_path,
    }


@router.get("/library/groups")
async def library_groups():
    lib_path = JellyfinConfig.get_music_library_path()
    if not os.path.isdir(lib_path):
        return {"groups": [], "library_path": lib_path}
    songs = scan_music_files(lib_path)
    return {**build_library_groups_response(songs), "library_path": lib_path}


@router.get("/library/stream")
async def library_stream(path: str = Query(..., description="Absolute path to file within music library")):
    lib_path = JellyfinConfig.get_music_library_path()
    norm_lib = os.path.normpath(os.path.realpath(lib_path))
    norm_path = os.path.normpath(os.path.realpath(path))

    if not norm_path.startswith(norm_lib + "/") and norm_path != norm_lib:
        return api_error("PATH_TRAVERSAL_BLOCKED", "Path is outside the music library.", 403)

    if not os.path.isfile(norm_path):
        return api_error("FILE_NOT_FOUND", "File not found.", 404)

    filename = os.path.basename(norm_path)
    return FileResponse(path=norm_path, filename=filename, media_type="application/octet-stream")
