
from __future__ import annotations

import os
import collections
import random
from typing import Dict, List, Optional

from PyQt5.QtCore import QThread, pyqtSignal


# ─── helpers ──────────────────────────────────────────────────────

_AUDIO_EXTS = {".mp3", ".m4a", ".mp4", ".flac", ".wav", ".ogg"}
_SKIP_ARTISTS = {"unknown artist", "unknown", ""}
_SKIP_GENRES  = {"unknown", ""}

# Title patterns that indicate extended / deluxe releases
EXTENDED_KEYWORDS = frozenset([
    "extended", "deluxe", "special edition", "expanded",
    "anniversary edition", "remastered edition", "complete edition",
])


def is_extended_release(title: str) -> bool:
    """Return True if the album title looks like a deluxe/extended release."""
    tl = title.lower()
    return any(kw in tl for kw in EXTENDED_KEYWORDS)


# ─── RecommenderThread ────────────────────────────────────────────

class RecommenderThread(QThread):
    """
    Signals
    -------
    recommendations_ready(queries: list[str])
        Top search query strings derived from the preference map.
    preference_map_ready(pref_map: dict)
        Raw tag → score map for optional display / debugging.
    progress(current: int, total: int)
    error(message: str)
    """

    recommendations_ready = pyqtSignal(list)   # list[str]
    preference_map_ready  = pyqtSignal(dict)
    progress              = pyqtSignal(int, int)
    error                 = pyqtSignal(str)

    def __init__(
        self,
        download_path: str,
        max_results:   int = 10,
        randomise:     bool = False,   # True → shuffle top results for "Refresh"
    ):
        super().__init__()
        self.download_path = download_path
        self.max_results   = max_results
        self.randomise     = randomise
        self._stop         = False

    def stop(self):
        self._stop = True

    # ── main run ──────────────────────────────────────────────

    def run(self):
        try:
            songs = self._scan_library()
            if not songs:
                self.recommendations_ready.emit([])
                return

            pref_map = self._build_preference_map(songs)
            self.preference_map_ready.emit(pref_map)

            queries = self._generate_queries(pref_map)
            self.recommendations_ready.emit(queries)
        except Exception as exc:
            self.error.emit(str(exc))

    # ── private: library scan ─────────────────────────────────

    def _scan_library(self) -> List[Dict]:
        try:
            from app.desktop.utils.metadata import get_audio_metadata
        except ImportError:
            return []

        all_files: List[str] = []
        for root, _, files in os.walk(self.download_path):
            for f in files:
                if os.path.splitext(f)[1].lower() in _AUDIO_EXTS:
                    all_files.append(os.path.join(root, f))

        songs: List[Dict] = []
        total = len(all_files)
        for i, fp in enumerate(all_files):
            if self._stop:
                break
            try:
                meta = get_audio_metadata(fp)
                songs.append({
                    "title":  meta.get("title",  ""),
                    "artist": meta.get("artist", ""),
                    "album":  meta.get("album",  ""),
                    "genre":  meta.get("genre",  ""),
                    "year":   str(meta.get("year", "") or ""),
                })
            except Exception:
                pass
            self.progress.emit(i + 1, total)

        return songs

    # ── private: preference map ───────────────────────────────

    def _build_preference_map(self, songs: List[Dict]) -> Dict[str, int]:
        counts: Dict[str, int] = collections.Counter()

        for s in songs:
            # Artists — highest weight
            artist = (s.get("artist") or "").strip()
            if artist.lower() not in _SKIP_ARTISTS:
                counts[f"artist:{artist}"] += 4

            # Genres — medium weight (may be comma-separated)
            genre_raw = (s.get("genre") or "").strip()
            for g in genre_raw.split(","):
                g = g.strip()
                if g.lower() not in _SKIP_GENRES:
                    counts[f"genre:{g}"] += 2

            # Decade — low weight
            year_raw = (s.get("year") or "").strip()
            if year_raw:
                try:
                    decade = (int(year_raw[:4]) // 10) * 10
                    counts[f"decade:{decade}s"] += 1
                except ValueError:
                    pass

        return dict(counts)

    # ── private: query generation ─────────────────────────────

    def _generate_queries(self, pref_map: Dict[str, int]) -> List[str]:
        if not pref_map:
            return []

        sorted_tags = sorted(pref_map.items(), key=lambda x: x[1], reverse=True)

        artist_queries: List[str] = []
        genre_queries:  List[str] = []
        decade_queries: List[str] = []

        seen_artists: set = set()
        seen_genres:  set = set()
        seen_decades: set = set()

        for tag, _ in sorted_tags:
            if tag.startswith("artist:"):
                a = tag[7:]
                if a not in seen_artists:
                    seen_artists.add(a)
                    artist_queries.append(a)
            elif tag.startswith("genre:"):
                g = tag[6:]
                if g not in seen_genres:
                    seen_genres.add(g)
                    genre_queries.append(f"best {g} music")
            elif tag.startswith("decade:"):
                d = tag[7:]
                if d not in seen_decades:
                    seen_decades.add(d)
                    decade_queries.append(f"top hits {d}")

        # Interleave: 2 artists, 1 genre, 1 decade, repeat
        combined: List[str] = []
        ai, gi, di = 0, 0, 0
        while len(combined) < self.max_results:
            added = False
            for _ in range(2):
                if ai < len(artist_queries) and len(combined) < self.max_results:
                    combined.append(artist_queries[ai]); ai += 1; added = True
            if gi < len(genre_queries) and len(combined) < self.max_results:
                combined.append(genre_queries[gi]); gi += 1; added = True
            if di < len(decade_queries) and len(combined) < self.max_results:
                combined.append(decade_queries[di]); di += 1; added = True
            if not added:
                break

        if self.randomise and len(combined) > 3:
            # Shuffle the non-first items so "Refresh" gives different results
            first = combined[:1]
            rest  = combined[1:]
            random.shuffle(rest)
            combined = first + rest

        return combined[: self.max_results]