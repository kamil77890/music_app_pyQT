from __future__ import annotations

import math
from typing import Any

from app.logic.api_handler.handle_yt_discovery import (
    TOP_ARTIST_EXPLORE_SUFFIX_SOURCE,
    TOP_ARTIST_NEWEST_SOURCE,
    TOP_ARTIST_POPULAR_SOURCE,
    TOP_TITLE_NEWEST_SOURCE,
    TOP_TITLE_POPULAR_SOURCE,
    YT_EXPLORE_SOURCE,
)
from app.utils.music_utils import normalize


_FOCUS_SOURCE_ORDER = {
    TOP_ARTIST_POPULAR_SOURCE: 0,
    TOP_ARTIST_NEWEST_SOURCE: 1,
    TOP_ARTIST_EXPLORE_SUFFIX_SOURCE: 2,
    TOP_TITLE_POPULAR_SOURCE: 3,
    TOP_TITLE_NEWEST_SOURCE: 4,
}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _log_views(views: int) -> float:
    if views <= 0:
        return 0.0
    return min(1.0, math.log10(views + 1) / 8.0)


def _recency_score(published_at: str, profile: dict[str, Any]) -> float:
    if not published_at:
        return 0.5
    try:
        year = int(published_at[:4])
    except (ValueError, TypeError):
        return 0.5
    era_weights = profile.get("by_dimension", {}).get("era", {})
    if not era_weights:
        if year >= 2015:
            return 0.8
        return 0.5
    era_map = {
        "pre_80s": 1970, "80s": 1985, "90s": 1995,
        "2000s": 2005, "2010s": 2015, "2020s": 2022,
    }
    best = 0.0
    for era, weight in era_weights.items():
        era_year = era_map.get(era, 2000)
        dist = abs(year - era_year)
        closeness = max(0.0, 1.0 - dist / 30.0)
        best = max(best, closeness * weight)
    return best


def _focus_looks_related(focus: str, channel: str, title: str) -> bool:
    f = focus.lower().strip()
    if not f:
        return False
    c = (channel or "").lower()
    t = (title or "").lower()
    if f in c or f in t:
        return True
    if len(f) >= 4 and c and (c in f or f.split()[0] in c):
        return True
    return False


def _library_title_match_boost(library_title: str, candidate_title: str) -> float:
    nt = normalize(library_title or "")
    nct = normalize(candidate_title or "")
    if not nt or not nct:
        return 0.0
    if nt in nct or nct in nt:
        return 0.35
    wa, wb = set(nt.split()), set(nct.split())
    if not wa:
        return 0.0
    overlap = len(wa & wb) / len(wa)
    return 0.35 * min(1.0, overlap)


def _interest_terms_in_title(profile: dict[str, Any], title: str) -> float:
    tl = (title or "").lower()
    if not tl:
        return 0.0
    hits = 0
    for entry in profile.get("top_tags", [])[:10]:
        tag = entry.get("tag", "")
        for term in (tag, tag.replace("_", " ")):
            if len(term) >= 3 and term in tl:
                hits += 1
                break
    for entry in profile.get("top_titles", [])[:10]:
        raw = (entry.get("title") or "").strip()
        if not raw:
            continue
        for w in set(normalize(raw).split()):
            if len(w) >= 4 and w in tl:
                hits += 1
                break
    return min(1.0, hits * 0.15)


def score_candidate(
    candidate: dict[str, Any],
    profile: dict[str, Any],
    library_artists: set[str],
) -> float:
    profile_tags = set(profile.get("tag_histogram", {}).keys())
    cand_tags = set(candidate.get("tags") or [])
    if candidate.get("matchedTags"):
        cand_tags |= set(candidate["matchedTags"])

    tag_overlap = _jaccard(profile_tags, cand_tags) if cand_tags else 0.25
    interest_hint = _interest_terms_in_title(profile, candidate.get("title", ""))
    tag_overlap = min(1.0, tag_overlap + interest_hint)

    lt_focus = (candidate.get("library_title_focus") or "").strip()
    if lt_focus:
        tag_overlap = min(1.0, tag_overlap + _library_title_match_boost(
            lt_focus, candidate.get("title", "")
        ))

    channel = (candidate.get("artist") or "").strip().lower()
    title = (candidate.get("title") or "").strip()
    focus = (candidate.get("library_artist_focus") or "").strip().lower()

    if focus and _focus_looks_related(focus, channel, title):
        artist_fit = 1.0
    elif focus:
        artist_fit = 0.35
    elif channel and channel not in library_artists:
        artist_fit = 1.0
    else:
        artist_fit = 0.35

    source = candidate.get("source", "")
    high_trust = {
        TOP_ARTIST_POPULAR_SOURCE,
        TOP_ARTIST_NEWEST_SOURCE,
        TOP_TITLE_POPULAR_SOURCE,
        TOP_TITLE_NEWEST_SOURCE,
    }
    if source in high_trust:
        source_fit = 1.0
    elif source == TOP_ARTIST_EXPLORE_SUFFIX_SOURCE:
        source_fit = 0.92
    elif source == YT_EXPLORE_SOURCE:
        source_fit = 0.65
    else:
        source_fit = 0.55

    views = int(candidate.get("viewCount") or 0)
    engagement = _log_views(views)

    recency = _recency_score(candidate.get("publishedAt", ""), profile)

    score = (
        tag_overlap * 30.0
        + artist_fit * 25.0
        + source_fit * 20.0
        + engagement * 15.0
        + recency * 10.0
    )
    return round(min(100.0, score), 2)


def rank_candidates(
    candidates: list[dict[str, Any]],
    profile: dict[str, Any],
    library_songs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    library_artists = {
        (s.get("artist") or "").strip().lower()
        for s in library_songs
        if s.get("artist")
    }
    excluded_ids = set(profile.get("excluded_video_ids", []))

    focus_sources = {
        TOP_ARTIST_POPULAR_SOURCE,
        TOP_ARTIST_NEWEST_SOURCE,
        TOP_ARTIST_EXPLORE_SUFFIX_SOURCE,
        TOP_TITLE_POPULAR_SOURCE,
        TOP_TITLE_NEWEST_SOURCE,
    }
    scored: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for c in candidates:
        vid = c.get("videoId")
        if vid and vid in excluded_ids:
            continue
        if vid and vid in seen_ids:
            continue
        if vid:
            seen_ids.add(vid)
        row = dict(c)
        row["score"] = score_candidate(row, profile, library_artists)
        scored.append(row)

    focus_rows = [r for r in scored if r.get("source") in focus_sources]
    rest = [r for r in scored if r.get("source") not in focus_sources]

    def focus_sort_key(x: dict[str, Any]):
        kind_primary = 0 if x.get("focus_kind") == "artist" else 1
        ar = x.get("library_artist_rank")
        tr = x.get("library_title_rank")
        if x.get("focus_kind") == "artist" and ar is not None:
            rank_key = ar
        elif x.get("focus_kind") == "title" and tr is not None:
            rank_key = tr
        else:
            rank_key = 99
        type_order = _FOCUS_SOURCE_ORDER.get(x.get("source"), 9)
        views = int(x.get("viewCount") or 0)
        pub = x.get("publishedAt") or ""
        if x.get("source") in (
            TOP_ARTIST_POPULAR_SOURCE,
            TOP_TITLE_POPULAR_SOURCE,
            TOP_ARTIST_EXPLORE_SUFFIX_SOURCE,
        ):
            tie = -views
        else:
            tie = pub
        return (kind_primary, rank_key, type_order, tie)

    focus_rows.sort(key=focus_sort_key)
    rest.sort(key=lambda x: -x.get("score", 0))
    return focus_rows + rest
