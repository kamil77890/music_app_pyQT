"""
SearchThread — QThread for non-blocking YouTube search
with album / official-playlist detection.

Signals
───────
results_ready(songs: list, albums: list, playlists: list, next_page_token: str)
    Emitted when the full search (songs + album detection) completes.
    - songs    : list of SongObject-compatible dicts
    - albums   : list of AlbumObject dicts (high-probability album playlists)
    - playlists: list of raw playlist dicts (lower-confidence)
    - next_page_token: str or None

album_tracks_ready(playlist_id: str, tracks: list)
    Emitted after `fetch_album_tracks(playlist_id)` resolves.

thumbnail_ready(video_id: str, pixmap: QPixmap)
    Emitted per-thumbnail as they load asynchronously.

error(message: str)
    Emitted on any fatal error.

progress(current: int, total: int, label: str)
    Optional progress updates.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import QThread, pyqtSignal, QMutex, QMutexLocker
from PyQt5.QtGui import QPixmap

# ── Keyword patterns that strongly suggest an "album" playlist ──
_ALBUM_STRONG_PATTERNS = [
    r"\bfull\s+album\b",
    r"\bofficial\s+album\b",
    r"\balbum\s+stream\b",
    r"\bfull\s+lp\b",
    r"\bfull\s+ep\b",
    r"\bdeluxe\s+edition\b",
    r"\bspecial\s+edition\b",
    r"\bplatinum\s+edition\b",
]
_ALBUM_WEAK_PATTERNS = [
    r"\balbum\b",
    r"\bep\b",
    r"\bplaylist\b",
    r"\bcomplete\s+collection\b",
    r"\bdiscography\b",
]
_OFFICIAL_CHANNEL_MARKERS = [
    "official",
    "vevo",
    "records",
    "music",
    "topic",
]


def _score_playlist_as_album(item: Dict[str, Any]) -> int:
    """
    Return a confidence score 0–100 for how likely `item` represents a
    proper music album.  Score ≥ 60 → AlbumCard; 30–59 → playlist card.
    """
    score = 0
    snippet = item.get("snippet", {})
    title   = (snippet.get("title", "") or "").lower()
    channel = (snippet.get("channelTitle", "") or "").lower()

    # strong title keywords
    for pat in _ALBUM_STRONG_PATTERNS:
        if re.search(pat, title, re.I):
            score += 40
            break

    # weak title keywords
    for pat in _ALBUM_WEAK_PATTERNS:
        if re.search(pat, title, re.I):
            score += 15
            break

    # official channel markers
    for marker in _OFFICIAL_CHANNEL_MARKERS:
        if marker in channel:
            score += 20
            break

    # track-count hint (itemCount in contentDetails)
    item_count = (
        item.get("contentDetails", {}).get("itemCount", 0) or 0
    )
    if 4 <= item_count <= 30:
        score += 15
    elif item_count > 30:
        score += 5   # likely just a big playlist, not an album

    return min(score, 100)


def _parse_album_type(title: str) -> str:
    t = title.lower()
    if "ep" in t or "e.p" in t:
        return "EP"
    if "single" in t:
        return "SINGLE"
    if "live" in t:
        return "LIVE"
    return "ALBUM"


def _fmt_duration(iso: str) -> str:
    """Convert ISO 8601 duration (PT3M45S) → '3:45'."""
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return ""
    h, mi, s = (int(x or 0) for x in m.groups())
    if h:
        return f"{h}:{mi:02d}:{s:02d}"
    return f"{mi}:{s:02d}"


# ─────────────────────────────────────────────────────────────────
#  SearchThread
# ─────────────────────────────────────────────────────────────────
class SearchThread(QThread):
    """
    Background worker that:
    1. Searches YouTube for videos matching `query`.
    2. Fetches detailed video data (views, duration, tags).
    3. In parallel, searches for playlists and scores them as albums.
    4. Emits `results_ready` with separated songs / albums / playlists.
    """

    results_ready     = pyqtSignal(list, list, list, str)   # songs, albums, playlists, next_token
    album_tracks_ready = pyqtSignal(str, list)               # playlist_id, tracks
    thumbnail_ready   = pyqtSignal(str, object)              # video_id, QPixmap
    error             = pyqtSignal(str)
    progress          = pyqtSignal(int, int, str)

    def __init__(
        self,
        query: str,
        page_token: str = "",
        max_results: int = 20,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.query        = query
        self.page_token   = page_token
        self.max_results  = max_results
        self._stop_flag   = False
        self._mutex       = QMutex()

    def stop(self) -> None:
        with QMutexLocker(self._mutex):
            self._stop_flag = True

    def _stopped(self) -> bool:
        with QMutexLocker(self._mutex):
            return self._stop_flag

    # ── main run ───────────────────────────────────────────────

    def run(self) -> None:
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._async_run())
            loop.close()
        except Exception as exc:
            self.error.emit(str(exc))

    async def _async_run(self) -> None:
        from app.desktop.config import config
        import asyncio

        query = self.query.strip()
        if not query:
            self.results_ready.emit([], [], [], "")
            return

        self.progress.emit(0, 3, "Searching songs…")

        # Step 1 – video search + detail fetch
        songs, next_token = await self._search_videos(query)
        if self._stopped():
            return

        self.progress.emit(1, 3, "Detecting albums…")

        # Step 2 – playlist/album search (parallel)
        raw_playlists = await self._search_playlists(query)
        if self._stopped():
            return

        # Step 3 – score and separate albums vs playlists
        albums    = []
        playlists = []
        for pl in raw_playlists:
            score = _score_playlist_as_album(pl)
            obj   = self._build_album_object(pl, score)
            if score >= 60:
                albums.append(obj)
            elif score >= 30:
                playlists.append(obj)

        self.progress.emit(3, 3, "Done")
        self.results_ready.emit(songs, albums, playlists, next_token or "")

    # ── video search ───────────────────────────────────────────

    async def _search_videos(self, query: str):
        from app.logic.api_handler.handle_yt import get_song_by_string
        try:
            data = await get_song_by_string(query, self.page_token or None)
            return data.get("songs", []), data.get("nextPageToken")
        except Exception as exc:
            self.error.emit(f"Video search failed: {exc}")
            return [], None

    # ── playlist search ────────────────────────────────────────

    async def _search_playlists(self, query: str) -> List[Dict]:
        from app.logic.api_handler.handle_yt_service import create_youtube_service
        try:
            yt = create_youtube_service()
            resp = yt.search().list(
                q=query,
                part="snippet",
                maxResults=6,
                type="playlist",
            ).execute()
            items = resp.get("items", [])

            # enrich with contentDetails (itemCount)
            if items:
                ids = ",".join(
                    i.get("id", {}).get("playlistId", "") for i in items
                    if i.get("id", {}).get("playlistId")
                )
                if ids:
                    detail = yt.playlists().list(
                        part="contentDetails,snippet",
                        id=ids,
                    ).execute()
                    detail_map = {
                        d["id"]: d for d in detail.get("items", [])
                    }
                    for item in items:
                        pid = item.get("id", {}).get("playlistId", "")
                        if pid in detail_map:
                            item["contentDetails"] = detail_map[pid].get(
                                "contentDetails", {}
                            )
            return items
        except Exception as exc:
            # don't fail the whole search just for playlists
            return []

    # ── album object builder ───────────────────────────────────

    @staticmethod
    def _build_album_object(item: Dict, score: int) -> Dict:
        snippet = item.get("snippet", {})
        pl_id   = item.get("id", {}).get("playlistId", "")
        title   = snippet.get("title", "Unknown Album")
        channel = snippet.get("channelTitle", "")

        thumbnails = snippet.get("thumbnails", {})
        thumb_url  = (
            thumbnails.get("high", {}).get("url")
            or thumbnails.get("medium", {}).get("url")
            or thumbnails.get("default", {}).get("url")
            or ""
        )

        item_count = item.get("contentDetails", {}).get("itemCount", 0) or 0

        return {
            "playlist_id"   : pl_id,
            "title"         : title,
            "artist"        : channel,
            "track_count"   : item_count,
            "album_type"    : _parse_album_type(title),
            "thumbnail_url" : thumb_url,
            "confidence"    : score,
        }


# ─────────────────────────────────────────────────────────────────
#  AlbumTracksThread
# ─────────────────────────────────────────────────────────────────
class AlbumTracksThread(QThread):
    """
    Fetches all tracks for a given playlist_id via playlistItems().list(),
    then enriches with video details (duration, view count).

    Emits:
        tracks_ready(playlist_id: str, tracks: list[dict])
        error(message: str)
    """

    tracks_ready = pyqtSignal(str, list)
    error        = pyqtSignal(str)

    MAX_PAGES = 5   # safety cap

    def __init__(self, playlist_id: str, parent=None) -> None:
        super().__init__(parent)
        self.playlist_id = playlist_id
        self._stop_flag  = False

    def stop(self) -> None:
        self._stop_flag = True

    def run(self) -> None:
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._async_run())
            loop.close()
        except Exception as exc:
            self.error.emit(str(exc))

    async def _async_run(self) -> None:
        from app.logic.api_handler.handle_yt_service import create_youtube_service
        try:
            yt       = create_youtube_service()
            tracks   = []
            token    = None
            pages    = 0

            while pages < self.MAX_PAGES:
                if self._stop_flag:
                    return

                kwargs = dict(
                    part           = "snippet,contentDetails",
                    playlistId     = self.playlist_id,
                    maxResults     = 50,
                )
                if token:
                    kwargs["pageToken"] = token

                resp  = yt.playlistItems().list(**kwargs).execute()
                items = resp.get("items", [])

                # get video ids for detail fetch
                vid_ids = [
                    i["contentDetails"]["videoId"]
                    for i in items
                    if i.get("contentDetails", {}).get("videoId")
                ]

                if vid_ids:
                    detail_resp = yt.videos().list(
                        part="snippet,contentDetails",
                        id=",".join(vid_ids),
                    ).execute()
                    detail_map = {
                        v["id"]: v for v in detail_resp.get("items", [])
                    }
                else:
                    detail_map = {}

                for i, item in enumerate(items):
                    vid_id   = item.get("contentDetails", {}).get("videoId", "")
                    detail   = detail_map.get(vid_id, {})
                    snip     = item.get("snippet", {})
                    d_snip   = detail.get("snippet", {})
                    d_cont   = detail.get("contentDetails", {})

                    thumb_url = (
                        d_snip.get("thumbnails", {}).get("high", {}).get("url")
                        or snip.get("thumbnails", {}).get("high", {}).get("url")
                        or ""
                    )

                    tracks.append({
                        "video_id"      : vid_id,
                        "title"         : snip.get("title", "Unknown"),
                        "artist"        : d_snip.get("channelTitle", ""),
                        "album_name"    : "",     # set by caller
                        "track_number"  : len(tracks) + 1,
                        "duration"      : _fmt_duration(d_cont.get("duration", "")),
                        "high_res_thumbnail": thumb_url,
                    })

                token = resp.get("nextPageToken")
                if not token:
                    break
                pages += 1

            self.tracks_ready.emit(self.playlist_id, tracks)

        except Exception as exc:
            self.error.emit(f"Album track fetch failed: {exc}")