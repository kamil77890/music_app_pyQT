from __future__ import annotations

import re
import asyncio
from typing import Any, Dict, List, Optional

from googleapiclient.errors import HttpError

from app.exceptions.youtube_errors import YouTubeAPIError
from app.logic.api_handler.handle_yt_service import create_youtube_service
from app.utils.youtube_error_handler import youtube_api_error_handler
from app.models.yt_convert.convert_video_item import convert_video_item as _base_convert


# ─────────────────────────────────────────────────────────────────
#  SongObject — extended schema
# ─────────────────────────────────────────────────────────────────

def build_song_object(
    yt_item: Dict[str, Any],
    index: int = 0,
    album_name: str = "",
    track_number: int = 0,
) -> Dict[str, Any]:
    base = _base_convert(yt_item, index)

    snippet    = yt_item.get("snippet", {})
    thumbnails = snippet.get("thumbnails", {})
    content    = yt_item.get("contentDetails", {})
    statistics = yt_item.get("statistics", {})

    high_res_url = (
        thumbnails.get("maxres", {}).get("url")
        or thumbnails.get("high",   {}).get("url")
        or thumbnails.get("medium", {}).get("url")
        or thumbnails.get("default", {}).get("url")
        or base.get("thumbnail", "")
        or ""
    )

    base.update({
        "album_name"         : album_name,
        "track_number"       : track_number or (index + 1),
        "high_res_thumbnail" : high_res_url,
        "view_count"         : int(statistics.get("viewCount", 0) or 0),
        "like_count"         : int(statistics.get("likeCount",  0) or 0),
        "duration_iso"       : content.get("duration", ""),
    })
    return base


# ─────────────────────────────────────────────────────────────────
#  Album-detection helpers
# ─────────────────────────────────────────────────────────────────

_ALBUM_PATTERNS = [
    r"\bfull[\s\-]album\b",
    r"\bofficial[\s\-]album\b",
    r"\balbum[\s\-]stream\b",
    r"\bfull[\s\-](lp|ep)\b",
    r"\bdeluxe[\s\-]edition\b",
    r"\bplatinum[\s\-]edition\b",
    r"\bspecial[\s\-]edition\b",
    r"\balbum\b",
    r"\bep\b",
    r"\bcomplete[\s\-]discography\b",
]

_OFFICIAL_CHANNEL_KEYWORDS = {
    "official", "vevo", "records", "music", "topic",
    "entertainment", "sony", "universal", "warner",
}


def score_playlist_as_album(playlist_item: Dict[str, Any], item_count: int = 0) -> int:
    score   = 0
    snippet = playlist_item.get("snippet", {})
    title   = (snippet.get("title",        "") or "").lower()
    channel = (snippet.get("channelTitle", "") or "").lower()

    strong = _ALBUM_PATTERNS[:6]
    weak   = _ALBUM_PATTERNS[6:]

    for pat in strong:
        if re.search(pat, title, re.I):
            score += 35
            break

    for pat in weak:
        if re.search(pat, title, re.I):
            score += 15
            break

    for marker in _OFFICIAL_CHANNEL_KEYWORDS:
        if marker in channel:
            score += 25
            break

    if 4 <= item_count <= 30:
        score += 15
    elif 31 <= item_count <= 80:
        score += 5

    return min(score, 100)


def _album_type(title: str) -> str:
    t = title.lower()
    if re.search(r"\bep\b|e\.p\.", t):
        return "EP"
    if "single" in t:
        return "SINGLE"
    if "live" in t:
        return "LIVE"
    if "mix" in t or "playlist" in t:
        return "PLAYLIST"
    return "ALBUM"


def _build_album_obj(pl: Dict, score: int, item_count: int) -> Dict:
    snippet = pl.get("snippet", {})
    pid     = pl.get("id", {}).get("playlistId", "")
    title   = snippet.get("title", "Unknown Album")
    channel = snippet.get("channelTitle", "")
    thumbs  = snippet.get("thumbnails", {})
    thumb   = (
        thumbs.get("high",   {}).get("url")
        or thumbs.get("medium", {}).get("url")
        or thumbs.get("default", {}).get("url")
        or ""
    )
    return {
        "playlist_id"  : pid,
        "title"        : title,
        "artist"       : channel,
        "track_count"  : item_count,
        "album_type"   : _album_type(title),
        "thumbnail_url": thumb,
        "confidence"   : score,
    }


# ─────────────────────────────────────────────────────────────────
#  Deep search: videos + album detection
# ─────────────────────────────────────────────────────────────────

@youtube_api_error_handler
async def deep_search(
    query: str,
    page_token: str = None,
    max_results: int = 20,
) -> Dict[str, Any]:
    yt = create_youtube_service()

    # 1. video search
    video_resp = yt.search().list(
        q         = query,
        part      = "snippet",
        maxResults= max_results,
        type      = "video",
        pageToken = page_token or None,
    ).execute()

    raw_videos = video_resp.get("items", [])
    next_token = video_resp.get("nextPageToken")

    # 2. detailed video data
    video_ids = ",".join(
        v["id"]["videoId"] for v in raw_videos
        if v.get("id", {}).get("videoId")
    )
    songs = []
    if video_ids:
        detail_resp = yt.videos().list(
            part="snippet,contentDetails,statistics",
            id=video_ids,
        ).execute()
        songs = [
            build_song_object(item, idx)
            for idx, item in enumerate(detail_resp.get("items", []))
        ]

    # 3. playlist / album search
    pl_resp = yt.search().list(
        q         = query,
        part      = "snippet",
        maxResults= 8,
        type      = "playlist",
    ).execute()

    raw_playlists = pl_resp.get("items", [])

    if raw_playlists:
        pl_ids = ",".join(
            p.get("id", {}).get("playlistId", "")
            for p in raw_playlists
            if p.get("id", {}).get("playlistId")
        )
        if pl_ids:
            pl_detail = yt.playlists().list(
                part="contentDetails,snippet",
                id=pl_ids,
            ).execute()
            detail_map = {d["id"]: d for d in pl_detail.get("items", [])}
            for pl in raw_playlists:
                pid = pl.get("id", {}).get("playlistId", "")
                if pid in detail_map:
                    pl["contentDetails"] = detail_map[pid].get("contentDetails", {})

    albums    = []
    playlists = []
    for pl in raw_playlists:
        item_count = pl.get("contentDetails", {}).get("itemCount", 0) or 0
        s   = score_playlist_as_album(pl, item_count)
        obj = _build_album_obj(pl, s, item_count)
        if s >= 60:
            albums.append(obj)
        elif s >= 30:
            playlists.append(obj)

    return {
        "songs"        : songs,
        "albums"       : albums,
        "playlists"    : playlists,
        "nextPageToken": next_token,
    }


# ─────────────────────────────────────────────────────────────────
#  Album track fetcher
# ─────────────────────────────────────────────────────────────────

@youtube_api_error_handler
async def fetch_album_tracks(
    playlist_id: str,
    album_name: str = "",
    max_pages: int  = 5,
) -> List[Dict[str, Any]]:
    yt     = create_youtube_service()
    tracks: List[Dict] = []
    token:  Optional[str] = None
    pages  = 0

    while pages < max_pages:
        kwargs: Dict[str, Any] = dict(
            part      = "snippet,contentDetails",
            playlistId= playlist_id,
            maxResults= 50,
        )
        if token:
            kwargs["pageToken"] = token

        resp  = yt.playlistItems().list(**kwargs).execute()
        items = resp.get("items", [])

        vid_ids = [
            i["contentDetails"]["videoId"]
            for i in items
            if i.get("contentDetails", {}).get("videoId")
        ]
        detail_map: Dict[str, Dict] = {}
        if vid_ids:
            dr = yt.videos().list(
                part="snippet,contentDetails,statistics",
                id=",".join(vid_ids),
            ).execute()
            detail_map = {v["id"]: v for v in dr.get("items", [])}

        for pl_item in items:
            vid_id = pl_item.get("contentDetails", {}).get("videoId", "")
            detail = detail_map.get(vid_id, {})
            track  = build_song_object(
                yt_item     = detail if detail else pl_item,
                index       = len(tracks),
                album_name  = album_name,
                track_number= len(tracks) + 1,
            )
            track["id"] = {"videoId": vid_id}
            tracks.append(track)

        token = resp.get("nextPageToken")
        if not token:
            break
        pages += 1

    return tracks


# ─────────────────────────────────────────────────────────────────
#  Synchronous wrappers for QThread.run()
# ─────────────────────────────────────────────────────────────────

def run_deep_search(query: str, page_token: str = "") -> Dict[str, Any]:
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(deep_search(query, page_token or None))
    finally:
        loop.close()


def run_fetch_album_tracks(playlist_id: str, album_name: str = "") -> List[Dict]:
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(fetch_album_tracks(playlist_id, album_name))
    finally:
        loop.close()