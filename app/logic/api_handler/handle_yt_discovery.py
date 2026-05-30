from __future__ import annotations

import logging
import random
import re
from typing import Any

from app.logic.api_handler.handle_yt_service import create_youtube_service
from app.logic.recommendations.resolver import cover_url
from app.logic.tags.universal_tags import get_dimension
from app.utils.youtube_error_handler import youtube_api_error_handler

log = logging.getLogger(__name__)


def _snippet_to_candidate(item: dict[str, Any], source: str) -> dict[str, Any] | None:
    vid = item.get("id", {}).get("videoId")
    if not vid:
        return None
    snippet = item.get("snippet", {})
    return {
        "videoId": vid,
        "title": snippet.get("title", ""),
        "artist": snippet.get("channelTitle", ""),
        "channelId": snippet.get("channelId", ""),
        "publishedAt": snippet.get("publishedAt", ""),
        "coverUrl": cover_url(vid),
        "source": source,
        "reason": f"Discovered via {source}",
        "tags": [],
        "viewCount": 0,
    }


@youtube_api_error_handler
def search_by_query(
    query: str,
    max_results: int = 5,
    *,
    order: str = "relevance",
    page_token: str | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    youtube = create_youtube_service()
    req: dict[str, Any] = {
        "q": query,
        "part": "snippet",
        "type": "video",
        "maxResults": min(max_results, 50),
        "order": order,
    }
    if page_token:
        req["pageToken"] = page_token
    resp = youtube.search().list(**req).execute()
    results = []
    for item in resp.get("items", []):
        c = _snippet_to_candidate(item, "tag_search")
        if c:
            c["searchQuery"] = query
            c["searchOrder"] = order
            results.append(c)
    return results, resp.get("nextPageToken")


def search_by_query_simple(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    rows, _ = search_by_query(query, max_results)
    return rows


@youtube_api_error_handler
def search_related_videos(
    video_id: str,
    max_results: int = 5,
    page_token: str | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """
    YouTube removed relatedToVideoId (Aug 2023). Fallback: search by seed
    video channel + title keywords, and same-channel recent uploads.
    """
    youtube = create_youtube_service()
    enriched = enrich_videos([video_id])
    meta = enriched.get(video_id, {})
    channel_id = meta.get("channelId", "")
    channel_title = (meta.get("artist") or "").strip()
    title = (meta.get("title") or "").strip()

    results: list[dict[str, Any]] = []
    seen: set[str] = {video_id}
    next_token: str | None = None

    if channel_id and not page_token:
        ch_req: dict[str, Any] = {
            "channelId": channel_id,
            "part": "snippet",
            "type": "video",
            "order": "relevance",
            "maxResults": min(max_results, 50),
        }
        ch_resp = youtube.search().list(**ch_req).execute()
        for item in ch_resp.get("items", []):
            c = _snippet_to_candidate(item, "related")
            if not c:
                continue
            vid = c.get("videoId")
            if vid in seen:
                continue
            seen.add(vid)
            c["seedVideoId"] = video_id
            c["reason"] = f"More from {channel_title or 'same channel'}"
            results.append(c)
        next_token = ch_resp.get("nextPageToken")

    if len(results) < max_results:
        query_parts = []
        if channel_title:
            query_parts.append(f'"{channel_title}"')
        if title:
            short = title[:60].replace('"', "")
            query_parts.append(short)
        query_parts.append("music")
        q = " ".join(query_parts).strip()
        if q:
            rows, tok = search_by_query(
                q,
                max(max_results - len(results), 5),
                order="relevance",
                page_token=page_token,
            )
            for c in rows:
                vid = c.get("videoId")
                if not vid or vid in seen:
                    continue
                seen.add(vid)
                c["source"] = "related"
                c["seedVideoId"] = video_id
                c["reason"] = f"Similar to {title[:40]}" if title else "Related search"
                results.append(c)
            if tok:
                next_token = tok

    return results[:max_results], next_token


def search_related_videos_simple(video_id: str, max_results: int = 5) -> list[dict[str, Any]]:
    rows, _ = search_related_videos(video_id, max_results)
    return rows


@youtube_api_error_handler
def enrich_videos(video_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not video_ids:
        return {}
    youtube = create_youtube_service()
    enriched: dict[str, dict[str, Any]] = {}
    unique = list(dict.fromkeys(video_ids))[:200]
    for i in range(0, len(unique), 50):
        chunk = unique[i : i + 50]
        resp = youtube.videos().list(
            part="snippet,contentDetails,statistics",
            id=",".join(chunk),
        ).execute()
        for item in resp.get("items", []):
            vid = item.get("id")
            if not vid:
                continue
            stats = item.get("statistics", {})
            snippet = item.get("snippet", {})
            enriched[vid] = {
                "viewCount": int(stats.get("viewCount", 0) or 0),
                "title": snippet.get("title", ""),
                "artist": snippet.get("channelTitle", ""),
                "channelId": snippet.get("channelId", ""),
                "publishedAt": snippet.get("publishedAt", ""),
            }
    return enriched


TOP_ARTIST_POPULAR_SOURCE = "library_top_artist_popular"
TOP_ARTIST_NEWEST_SOURCE = "library_top_artist_newest"
TOP_TITLE_POPULAR_SOURCE = "library_top_title_popular"
TOP_TITLE_NEWEST_SOURCE = "library_top_title_newest"
TOP_ARTIST_EXPLORE_SUFFIX_SOURCE = "library_artist_explore"
YT_EXPLORE_SOURCE = "yt_explore"


@youtube_api_error_handler
def search_music_videos(
    query: str,
    *,
    order: str,
    max_results: int,
    page_token: str | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    youtube = create_youtube_service()
    req: dict[str, Any] = {
        "q": query,
        "part": "snippet",
        "type": "video",
        "maxResults": min(max_results, 50),
        "order": order,
        "videoCategoryId": "10",
    }
    if page_token:
        req["pageToken"] = page_token
    resp = youtube.search().list(**req).execute()
    results = []
    for item in resp.get("items", []):
        c = _snippet_to_candidate(item, "music_search")
        if c:
            c["searchQuery"] = query
            c["searchOrder"] = order
            results.append(c)
    return results, resp.get("nextPageToken")


def search_music_videos_simple(
    query: str,
    *,
    order: str,
    max_results: int,
) -> list[dict[str, Any]]:
    rows, _ = search_music_videos(query, order=order, max_results=max_results)
    return rows


def _artist_search_query(artist_name: str, interest_hint: str = "") -> str:
    safe = (artist_name or "").strip().replace('"', "").replace("\\", "")
    base = f'"{safe}"'
    if interest_hint:
        return f"{base} {interest_hint} music"
    return f"{base} music"


def discover_from_library_top_artists(
    top_artists: list[dict[str, Any]],
    excluded_video_ids: set[str],
    *,
    interest_hint: str = "",
    primary_popular: int = 3,
    primary_newest: int = 3,
    extra_artists: int = 2,
    extra_popular: int = 2,
    extra_newest: int = 2,
) -> list[dict[str, Any]]:
    """
    For the most-listened library artists, pull YouTube results ordered by
    views (popular) and published date (newest). Excludes videos already in the library.
    """
    if not top_artists:
        return []

    all_rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    def take_ordered(artist: str, order: str, limit: int, source: str, artist_rank: int) -> None:
        nonlocal all_rows, seen
        if limit <= 0:
            return
        q = _artist_search_query(artist, interest_hint)
        batch = search_music_videos_simple(q, order=order, max_results=min(limit + 8, 15))
        added = 0
        for c in batch:
            vid = c.get("videoId")
            if not vid or vid in excluded_video_ids or vid in seen:
                continue
            seen.add(vid)
            c["source"] = source
            c["library_artist_focus"] = artist
            c["library_artist_rank"] = artist_rank
            c["focus_kind"] = "artist"
            c["reason"] = (
                f"Top {limit}-style popular picks on YouTube from your library's #{artist_rank + 1} artist ({artist})"
                if order == "viewCount"
                else f"Newest uploads matching your #{artist_rank + 1} library artist ({artist})"
            )
            all_rows.append(c)
            added += 1
            if added >= limit:
                break

    for rank, entry in enumerate(top_artists):
        artist = (entry.get("artist") or "").strip()
        if not artist:
            continue

        if rank == 0:
            take_ordered(artist, "viewCount", primary_popular, TOP_ARTIST_POPULAR_SOURCE, rank)
            take_ordered(artist, "date", primary_newest, TOP_ARTIST_NEWEST_SOURCE, rank)
            safe_primary = artist.replace('"', "").replace("\\", "").strip()
            if safe_primary:
                # Fewer suffix searches keeps per-request quota + latency down.
                for suf in (
                    " official audio",
                    " lyrics",
                ):
                    q = f'"{safe_primary}"{suf}'
                    order = random.choice(("relevance", "viewCount", "date"))
                    batch, ntok = search_music_videos(
                        q, order=order, max_results=12
                    )
                    for c in batch:
                        vid = c.get("videoId")
                        if not vid or vid in excluded_video_ids or vid in seen:
                            continue
                        seen.add(vid)
                        c["source"] = TOP_ARTIST_EXPLORE_SUFFIX_SOURCE
                        c["library_artist_focus"] = artist
                        c["library_artist_rank"] = rank
                        c["focus_kind"] = "artist"
                        c["reason"] = (
                            f'YouTube music search for your top artist: «{safe_primary}» ({suf.strip()})'
                        )
                        all_rows.append(c)
                    if ntok and random.random() < 0.35:
                        batch2, _ = search_music_videos(
                            q,
                            order=order,
                            max_results=8,
                            page_token=ntok,
                        )
                        for c in batch2:
                            vid = c.get("videoId")
                            if not vid or vid in excluded_video_ids or vid in seen:
                                continue
                            seen.add(vid)
                            c["source"] = TOP_ARTIST_EXPLORE_SUFFIX_SOURCE
                            c["library_artist_focus"] = artist
                            c["library_artist_rank"] = rank
                            c["focus_kind"] = "artist"
                            c["reason"] = (
                                f'YouTube music search (page 2) for «{safe_primary}» ({suf.strip()})'
                            )
                            all_rows.append(c)
        elif rank <= extra_artists:
            take_ordered(artist, "viewCount", extra_popular, TOP_ARTIST_POPULAR_SOURCE, rank)
            take_ordered(artist, "date", extra_newest, TOP_ARTIST_NEWEST_SOURCE, rank)
        else:
            break

    return all_rows


def _clean_title_for_query(title: str, max_len: int = 72) -> str:
    t = (title or "").strip()
    t = re.sub(
        r"\s*[\(\[]\s*(official|lyrics|audio|mv|music video|hd|4k)[^\)\]]*[\)\]]",
        "",
        t,
        flags=re.I,
    )
    t = re.split(r"\bfeat\.|\bft\.|\bfeaturing\b", t, maxsplit=1, flags=re.I)[0].strip()
    t = t.replace('"', "").replace("\\", "")
    if len(t) > max_len:
        cut = t[:max_len]
        t = cut.rsplit(" ", 1)[0] if " " in cut else cut
    return t or (title or "").strip()[:max_len]


def _title_search_query(title: str, artist: str, interest_hint: str) -> str:
    ct = _clean_title_for_query(title)
    parts: list[str] = []
    if ct:
        parts.append(f'"{ct}"')
    if artist:
        a = artist.strip().replace('"', "").replace("\\", "")
        if a:
            parts.append(f'"{a}"')
    if interest_hint:
        parts.append(interest_hint.strip())
    body = " ".join(parts).strip()
    if not body:
        return ""
    return f"{body} music"


def discover_from_library_titles(
    top_titles: list[dict[str, Any]],
    excluded_video_ids: set[str],
    *,
    interest_hint: str = "",
    depth: int = 4,
    popular_per: int = 1,
    newest_per: int = 1,
) -> list[dict[str, Any]]:
    """
    YouTube search using canonical titles from the library (plus dominant artist per title),
    ordered by view count (popular) and upload date (newest).
    """
    if not top_titles:
        return []

    all_rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    def take_for_title(
        display_title: str,
        artist: str,
        order: str,
        limit: int,
        source: str,
        title_rank: int,
    ) -> None:
        nonlocal all_rows, seen
        if limit <= 0:
            return
        q = _title_search_query(display_title, artist, interest_hint)
        if not q or q == "music":
            return
        batch = search_music_videos_simple(q, order=order, max_results=min(limit + 10, 15))
        added = 0
        for c in batch:
            vid = c.get("videoId")
            if not vid or vid in excluded_video_ids or vid in seen:
                continue
            seen.add(vid)
            c["source"] = source
            c["focus_kind"] = "title"
            c["library_title_focus"] = display_title
            c["library_title_rank"] = title_rank
            if artist:
                c["library_artist_focus"] = artist
            c["reason"] = (
                f"Popular YouTube results for your library title «{display_title}»"
                if order == "viewCount"
                else f"Newest uploads related to library title «{display_title}»"
            )
            all_rows.append(c)
            added += 1
            if added >= limit:
                break

    for rank, entry in enumerate(top_titles[:depth]):
        t = (entry.get("title") or "").strip()
        if not t:
            continue
        art = (entry.get("artist") or "").strip()
        take_for_title(t, art, "viewCount", popular_per, TOP_TITLE_POPULAR_SOURCE, rank)
        take_for_title(t, art, "date", newest_per, TOP_TITLE_NEWEST_SOURCE, rank)

    return all_rows


def build_tag_search_queries(profile: dict[str, Any], count: int = 4) -> list[str]:
    """YouTube search queries from taste profile (tags and/or library artists/titles only — no AI)."""
    queries: list[str] = []
    top_tags = [t["tag"] for t in profile.get("top_tags", [])[:8]]
    if top_tags:
        if len(top_tags) >= 2:
            queries.append(f"{' '.join(top_tags[:2]).replace('_', ' ')} music")
        if len(top_tags) >= 3:
            queries.append(f"{top_tags[0].replace('_', ' ')} {top_tags[2].replace('_', ' ')} songs")
            queries.append(
                f"{top_tags[1].replace('_', ' ')} {top_tags[2].replace('_', ' ')} mix"
            )
        energy = profile.get("energy_avg", "medium")
        queries.append(f"{top_tags[0].replace('_', ' ')} {energy} music")
        queries.append(f"{top_tags[0].replace('_', ' ')} playlist 2024")
        for tag in top_tags[:6]:
            dim = get_dimension(tag)
            label = tag.replace("_", " ")
            if dim == "genre":
                queries.append(f"best {label} songs")
                queries.append(f"{label} underground")
            elif dim == "mood":
                queries.append(f"{label} chill music")

    for entry in profile.get("top_artists", [])[:8]:
        if not entry.get("from_library") and entry.get("song_count", 0) <= 0:
            continue
        a = (entry.get("artist") or "").strip().replace('"', "").replace("\\", "")
        if not a or a.lower() in ("unknown artist", "unknown"):
            continue
        queries.append(f'"{a}" official audio')
        queries.append(f"{a} nightcore" if "nightcore" in str(profile.get("tag_histogram", {})).lower() else f"{a} songs")

    for entry in profile.get("top_titles", [])[:6]:
        t = _clean_title_for_query((entry.get("title") or "").strip())
        ar = (entry.get("artist") or "").strip().replace('"', "").replace("\\", "")
        if t and ar:
            queries.append(f'"{t}" "{ar}"')
        elif t:
            queries.append(f'"{t}" music video')

    if not queries:
        # Derive a fallback from the profile instead of a fixed term.
        top_tag = (profile.get("top_tags") or [{}])[0].get("tag", "")
        top_artist = ""
        for e in profile.get("top_artists", []):
            if e.get("artist"):
                top_artist = e["artist"]
                break
        derived = " ".join(p for p in (top_artist, top_tag.replace("_", " ")) if p).strip()
        if derived:
            queries.append(f"{derived} music")

    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        qn = q.strip().lower()
        if len(qn) < 3:
            continue
        if qn not in seen:
            seen.add(qn)
            out.append(q.strip())
        if len(out) >= count:
            break
    return out[:count]


def build_expanded_discovery_queries(profile: dict[str, Any], max_queries: int = 72) -> list[str]:
    """Broad query pool for extra search.list calls (deduped; caller shuffles / samples)."""
    pool: list[str] = []
    for e in profile.get("top_artists", [])[:8]:
        a = (e.get("artist") or "").strip()
        if not a:
            continue
        safe = a.replace('"', "").replace("\\", "")
        pool.extend([
            f'"{safe}" official audio',
            f'"{safe}" lyrics',
            f'"{safe}" best songs',
            f'"{safe}" remix',
            f'"{safe}" slowed reverb',
            f"{safe} type beat",
            f"{safe} live session",
            f"{safe} acoustic",
        ])
    for e in profile.get("top_titles", [])[:10]:
        t = _clean_title_for_query(e.get("title") or "")
        ar = (e.get("artist") or "").strip()
        if t and ar:
            pool.append(f'"{t}" "{ar}"')
            pool.append(f"{t} cover")
            pool.append(f"{t} remix {ar}")
        elif t:
            pool.append(f'"{t}" music')
    for tag_entry in (profile.get("top_tags") or [])[:10]:
        tg = (tag_entry.get("tag") or "").replace("_", " ")
        if tg:
            pool.append(f"{tg} music 2024")
            pool.append(f"best {tg} songs")
            pool.append(f"{tg} mix hour")
    pool.extend(build_tag_search_queries(profile, count=12))
    seen: set[str] = set()
    out: list[str] = []
    for q in pool:
        qn = q.strip().lower()
        if len(qn) < 3:
            continue
        if qn not in seen:
            seen.add(qn)
            out.append(q.strip())
        if len(out) >= max_queries:
            break
    return out


def run_exploratory_youtube_searches(
    queries: list[str],
    excluded_video_ids: set[str],
    *,
    num_queries: int = 14,
    take_per_query: int = 5,
    rng: random.Random | None = None,
) -> list[dict[str, Any]]:
    rng = rng or random.Random()
    pool = [q.strip() for q in queries if q and len(q.strip()) >= 3]
    if not pool:
        return []
    rng.shuffle(pool)
    picks = pool[: num_queries]
    seen: set[str] = set(excluded_video_ids)
    out: list[dict[str, Any]] = []
    orders = ("relevance", "viewCount", "date", "rating")
    for q in picks:
        order = rng.choice(orders)
        rows, tok = search_by_query(
            q,
            min(take_per_query + 8, 20),
            order=order,
        )
        per_q = 0
        for c in rows:
            vid = c.get("videoId")
            if not vid or vid in seen:
                continue
            seen.add(vid)
            c["source"] = YT_EXPLORE_SOURCE
            c["reason"] = f"YouTube explore ({order}): {q[:80]}"
            out.append(c)
            per_q += 1
            if per_q >= take_per_query:
                break
        if tok and rng.random() < 0.4 and per_q < take_per_query + 2:
            rows2, _ = search_by_query(
                q,
                10,
                order=order,
                page_token=tok,
            )
            for c in rows2:
                vid = c.get("videoId")
                if not vid or vid in seen:
                    continue
                seen.add(vid)
                c["source"] = YT_EXPLORE_SOURCE
                c["reason"] = f"YouTube explore page 2 ({order}): {q[:80]}"
                out.append(c)
                per_q += 1
                if per_q >= take_per_query + 3:
                    break
    return out
