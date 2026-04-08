
from __future__ import annotations

import os
import re
import collections
import random
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

from PyQt5.QtCore import QThread, pyqtSignal


# ─── helpers ──────────────────────────────────────────────────────

_AUDIO_EXTS = {".mp3", ".m4a", ".mp4", ".flac", ".wav", ".ogg"}
_SKIP_ARTISTS = {"unknown artist", "unknown", ""}
_SKIP_GENRES  = {"unknown", "", "unknown genre"}

# Title patterns that indicate extended / deluxe releases
EXTENDED_KEYWORDS = frozenset([
    "extended", "deluxe", "special edition", "expanded",
    "anniversary edition", "remastered edition", "complete edition",
])

# Artists to skip in recommendations (too generic)
_SKIP_ARTIST_PATTERNS = {"various artists", "various", "va-", "compilation"}


def is_extended_release(title: str) -> bool:
    """Return True if the album title looks like a deluxe/extended release."""
    tl = title.lower()
    return any(kw in tl for kw in EXTENDED_KEYWORDS)


def _parse_genres(genre_string: str) -> List[str]:
    """
    Parse genre string with multiple values separated by commas.
    "Rock, Pop, Alternative" → ["Rock", "Pop", "Alternative"]
    "Rock & Roll" → ["Rock & Roll"]
    """
    if not genre_string or genre_string.lower() in _SKIP_GENRES:
        return []
    
    # Split by common separators
    genres = []
    for part in re.split(r'[,;/]', genre_string):
        g = part.strip()
        if g and g.lower() not in _SKIP_GENRES:
            # Normalize common genres
            g_normalized = g.title() if not g.isupper() else g
            genres.append(g_normalized)
    
    return genres


def _extract_decade(year_str: str) -> Optional[str]:
    """
    Extract decade from year string.
    "1995" → "1990s"
    "2010-05-20" → "2010s"
    "(1985)" → "1980s"
    """
    if not year_str:
        return None
    
    # Try to find a 4-digit year
    match = re.search(r'(\d{4})', year_str)
    if not match:
        return None
    
    try:
        year = int(match.group(1))
        if year < 1900 or year > 2030:
            return None
        
        decade = (year // 10) * 10
        return f"{decade}s"
    except ValueError:
        return None


def _clean_artist_name(name: str) -> str:
    """
    Clean artist name for better matching.
    "The Beatles (Remastered)" → "The Beatles"
    "Artist Name [feat. X]" → "Artist Name"
    """
    if not name:
        return ""
    
    # Remove common suffixes in parentheses/brackets
    cleaned = re.sub(r'\s*[\(\[][^)\]]*[\)\]]', '', name).strip()
    
    # Remove "feat.", "ft.", "with", etc.
    cleaned = re.sub(r'\s*(feat\.?|ft\.?|with|pres\.?)\s+.*$', '', cleaned, flags=re.IGNORECASE).strip()
    
    return cleaned if cleaned else name


def _should_skip_artist(artist: str) -> bool:
    """Check if artist name should be skipped (too generic)."""
    if not artist:
        return True
    
    artist_lower = artist.lower().strip()
    if artist_lower in _SKIP_ARTISTS:
        return True
    
    # Check for generic patterns
    for pattern in _SKIP_ARTIST_PATTERNS:
        if pattern in artist_lower:
            return True
    
    return False


# ─── RecommenderThread ────────────────────────────────────────────

class RecommenderThread(QThread):
    """
    Signals
    -------
    popular_ready(queries: list[str], library_song_count: int)
        Search queries for popular/classic songs from user's library.
    new_ready(queries: list[str], library_song_count: int)
        Search queries for new releases (current/next year).
    preference_map_ready(pref_map: dict)
        Raw tag analysis for optional display / debugging.
    progress(current: int, total: int)
    error(message: str)
    """

    popular_ready      = pyqtSignal(list, int)  # popular queries, song count
    new_ready          = pyqtSignal(list, int)  # new release queries, song count
    preference_map_ready  = pyqtSignal(dict)
    progress              = pyqtSignal(int, int)
    error                 = pyqtSignal(str)

    def __init__(
        self,
        download_path: str,
        max_results:   int = 12,
        randomise:     bool = False,   # True → shuffle top results for "Refresh"
    ):
        super().__init__()
        self.download_path = download_path
        self.max_results   = max_results
        self.randomise     = randomise
        self._stop         = False
        self._last_tag_analysis = {}  # Store for access from main window

    def stop(self):
        self._stop = True

    # ── main run ──────────────────────────────────────────────

    def run(self):
        try:
            songs = self._scan_library()
            n_lib = len(songs)
            if not songs:
                self.popular_ready.emit([], 0)
                self.new_ready.emit([], 0)
                return

            tag_analysis = self._analyze_tags(songs)
            self._last_tag_analysis = tag_analysis  # Store for access from main window
            self.preference_map_ready.emit(tag_analysis)

            # Generate both popular and new queries
            popular_queries = self._generate_popular_queries(tag_analysis)
            new_queries = self._generate_new_queries(tag_analysis)
            
            self.popular_ready.emit(popular_queries, n_lib)
            self.new_ready.emit(new_queries, n_lib)
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
                
                # Clean and normalize data
                artist_raw = (meta.get("artist") or "").strip()
                artist_clean = _clean_artist_name(artist_raw)
                
                year_raw = (meta.get("year") or "").strip()
                decade = _extract_decade(year_raw)
                
                song_data = {
                    "title":  (meta.get("title") or "").strip(),
                    "artist": artist_clean,
                    "album":  (meta.get("album") or "").strip(),
                    "genre":  (meta.get("genre") or "").strip(),
                    "year":   year_raw,
                    "decade": decade,
                    "duration": meta.get("duration", 0),
                    "file_path": fp,
                }
                songs.append(song_data)
            except Exception:
                pass
            
            # Emit progress less frequently
            if total <= 1 or i == 0 or (i + 1) % 10 == 0 or (i + 1) == total:
                self.progress.emit(i + 1, total)

        return songs

    # ── private: tag analysis ─────────────────────────────────

    def _analyze_tags(self, songs: List[Dict]) -> Dict:
        """
        Comprehensive tag analysis to build a detailed preference profile.
        Returns a dictionary with artist, genre, decade, and album distributions.
        """
        artist_counts: Dict[str, int] = collections.Counter()
        genre_counts: Dict[str, int] = collections.Counter()
        decade_counts: Dict[str, int] = collections.Counter()
        album_counts: Dict[str, int] = collections.Counter()
        
        # Track which artists appear with which genres (for co-occurrence)
        artist_genre_map: Dict[str, Set[str]] = collections.defaultdict(set)
        
        for song in songs:
            # Artists (skip generic ones)
            artist = song.get("artist", "").strip()
            if artist and not _should_skip_artist(artist):
                artist_counts[artist] += 1
            
            # Genres (parse multiple genres)
            genre_raw = song.get("genre", "").strip()
            genres = _parse_genres(genre_raw)
            for genre in genres:
                genre_counts[genre] += 1
                if artist and not _should_skip_artist(artist):
                    artist_genre_map[artist].add(genre)
            
            # Decades
            decade = song.get("decade")
            if decade:
                decade_counts[decade] += 1
            
            # Albums (skip if no album name)
            album = song.get("album", "").strip()
            if album and album.lower() not in ("unknown", "unknown album", ""):
                album_counts[album] += 1
        
        # Build sorted lists
        top_artists = [artist for artist, _ in artist_counts.most_common()]
        top_genres = [genre for genre, _ in genre_counts.most_common()]
        top_decades = [decade for decade, _ in decade_counts.most_common()]
        top_albums = [album for album, _ in album_counts.most_common()]
        
        return {
            "artists": dict(artist_counts),
            "genres": dict(genre_counts),
            "decades": dict(decade_counts),
            "albums": dict(album_counts),
            "top_artists": top_artists[:10],  # Top 10 artists
            "top_genres": top_genres[:8],     # Top 8 genres
            "top_decades": top_decades[:5],   # Top 5 decades
            "top_albums": top_albums[:10],    # Top 10 albums
            "artist_genres": {k: list(v) for k, v in artist_genre_map.items()},
            "total_songs": len(songs),
        }

    # ── private: popular queries generation ──────────────────────

    def _generate_popular_queries(self, tag_analysis: Dict) -> List[str]:
        """
        Generate search queries for POPULAR/CLASSIC songs.
        Focus on: greatest hits, best-of, classics, essential tracks.
        Target: 7 queries
        """
        if not tag_analysis or tag_analysis.get("total_songs", 0) == 0:
            return []

        queries: List[str] = []
        seen: set = set()

        top_artists = tag_analysis.get("top_artists", [])[:5]
        top_genres = tag_analysis.get("top_genres", [])[:5]
        top_decades = tag_analysis.get("top_decades", [])[:3]
        top_albums = tag_analysis.get("top_albums", [])[:5]

        # ── Layer 1: Top Artists - Greatest Hits (4 queries) ────

        # 1. Top artist greatest hits
        if top_artists:
            artist1 = top_artists[0]
            query = f"{artist1} greatest hits"
            if query not in seen:
                queries.append(query)
                seen.add(query)
        
        # 2. Top artist most popular
        if len(top_artists) > 0:
            artist1 = top_artists[0]
            query = f"{artist1} most popular songs"
            if query not in seen:
                queries.append(query)
                seen.add(query)
        
        # 3. Second artist essential tracks
        if len(top_artists) > 1:
            artist2 = top_artists[1]
            query = f"{artist2} essential tracks"
            if query not in seen:
                queries.append(query)
                seen.add(query)
        
        # 4. Third artist greatest hits
        if len(top_artists) > 2:
            artist3 = top_artists[2]
            query = f"{artist3} greatest hits"
            if query not in seen:
                queries.append(query)
                seen.add(query)

        # ── Layer 2: Genre Classics (2 queries) ─────────────────

        # 5. Top genre classics
        if top_genres:
            genre = top_genres[0]
            query = f"best {genre} classics"
            if query not in seen:
                queries.append(query)
                seen.add(query)
        
        # 6. Second genre greatest songs
        if len(top_genres) > 1:
            genre = top_genres[1]
            query = f"{genre} greatest songs"
            if query not in seen:
                queries.append(query)
                seen.add(query)

        # ── Layer 3: Era + Album (1-2 queries) ──────────────────

        # 7. Decade best hits
        if top_genres and top_decades:
            genre = top_genres[0]
            decade = top_decades[0]
            query = f"{genre} {decade} best hits"
            if query not in seen:
                queries.append(query)
                seen.add(query)
        
        # 8. Popular album full
        if top_albums:
            for album in top_albums[:3]:
                if tag_analysis["albums"].get(album, 0) >= 3:
                    query = f"{album} full album"
                    if query not in seen:
                        queries.append(query)
                        seen.add(query)
                        break

        # ── Post-processing ─────────────────────────────────────

        # Filter quality
        queries = [q for q in queries if 5 < len(q) < 100]
        
        # Ensure diversity (max 2 from same artist)
        final_queries: List[str] = []
        artist_count: Dict[str, int] = collections.Counter()
        
        for query in queries:
            parts = query.split()
            if parts:
                potential_artist = parts[0]
                if artist_count[potential_artist] < 2:
                    final_queries.append(query)
                    artist_count[potential_artist] += 1
            else:
                final_queries.append(query)
        
        return final_queries[:7]

    # ── private: new releases queries generation ────────────────

    def _generate_new_queries(self, tag_analysis: Dict) -> List[str]:
        """
        Generate search queries for NEW RELEASES.
        Focus on: current year, next year, recent months.
        Target: 5 queries
        """
        if not tag_analysis or tag_analysis.get("total_songs", 0) == 0:
            return []

        queries: List[str] = []
        seen: set = set()

        top_genres = tag_analysis.get("top_genres", [])[:5]
        top_artists = tag_analysis.get("top_artists", [])[:3]
        
        # Get current date info
        now = datetime.now()
        current_year = now.year  # 2025
        next_year = current_year + 1  # 2026
        current_month = now.strftime("%B")  # "April"

        # ── Layer 1: New in Top Genres (3 queries) ──────────────

        # 1. Best new music in top genre (current + next year)
        if top_genres:
            genre = top_genres[0]
            query = f"best new {genre} {current_year} {next_year}"
            if query not in seen:
                queries.append(query)
                seen.add(query)
        
        # 2. New releases in second genre
        if len(top_genres) > 1:
            genre = top_genres[1]
            query = f"new {genre} releases {current_year} {next_year}"
            if query not in seen:
                queries.append(query)
                seen.add(query)
        
        # 3. Third genre new
        if len(top_genres) > 2:
            genre = top_genres[2]
            query = f"best new {genre} {current_year}"
            if query not in seen:
                queries.append(query)
                seen.add(query)

        # ── Layer 2: Current Trending (2 queries) ───────────────

        # 4. Genre hits current year
        if top_genres:
            genre = top_genres[0]
            query = f"{genre} hits {current_year}"
            if query not in seen:
                queries.append(query)
                seen.add(query)
        
        # 5. Very recent (this month) or underground new
        if len(top_genres) > 2:
            genre = top_genres[2]
            query = f"{genre} underground {current_year}"
            if query not in seen:
                queries.append(query)
                seen.add(query)
        elif top_genres:
            genre = top_genres[0]
            query = f"new {genre} {current_month} {current_year}"
            if query not in seen:
                queries.append(query)
                seen.add(query)

        # ── Post-processing ─────────────────────────────────────

        # Filter quality
        queries = [q for q in queries if 5 < len(q) < 100]
        
        # Remove duplicates
        final_queries = list(dict.fromkeys(queries))
        
        return final_queries[:5]
