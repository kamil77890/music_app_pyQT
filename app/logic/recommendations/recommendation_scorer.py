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

_HIGH_TRUST = frozenset({
    TOP_ARTIST_POPULAR_SOURCE,
    TOP_ARTIST_NEWEST_SOURCE,
    TOP_TITLE_POPULAR_SOURCE,
    TOP_TITLE_NEWEST_SOURCE,
    "subscription_feed",
    "notification",
    "oauth_music_liked",
    "oauth_similar",
    "reference_playlist",
})


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
        return 0.8 if year >= 2015 else 0.5
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
    return 0.35 * min(1.0, len(wa & wb) / len(wa))


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


def _behavioral_affinity(candidate: dict[str, Any], profile: dict[str, Any]) -> float:
    behavioral = profile.get("behavioral") or {}
    vid = candidate.get("videoId")
    channel = candidate.get("channelId") or ""
    artist = (candidate.get("artist") or "").lower()

    score = 0.0
    for v in behavioral.get("top_videos", []):
        if v.get("video_id") == vid:
            plays = v.get("play_count", 0)
            completes = v.get("complete_count", 0)
            ratio = v.get("avg_listen_ratio", 0)
            score = min(1.0, plays * 0.15 + completes * 0.25 + ratio * 0.4)
            break

    for ch in behavioral.get("top_channels", []):
        if ch.get("channel_id") == channel:
            score = max(score, min(1.0, ch.get("play_count", 0) * 0.1))
            break

    for a in behavioral.get("top_artists", []):
        if (a.get("artist") or "").lower() == artist:
            score = max(score, min(1.0, a.get("play_count", 0) * 0.12))
            break

    return score


def _negative_penalty(candidate: dict[str, Any], profile: dict[str, Any]) -> float:
    negative = profile.get("negative") or {}
    vid = candidate.get("videoId")
    channel = candidate.get("channelId") or ""
    artist = (candidate.get("artist") or "").lower()

    penalty = 0.0
    if vid in set(negative.get("disliked_video_ids", [])):
        penalty += 0.5
    if channel in set(negative.get("hidden_channels", [])):
        penalty += 0.6
    for entry in negative.get("disliked_artists", []):
        if (entry.get("artist") or "").lower() == artist:
            penalty += min(0.4, entry.get("count", 1) * 0.1)
    return min(0.6, penalty)


def _subscription_boost(candidate: dict[str, Any], profile: dict[str, Any]) -> float:
    weights = profile.get("channel_weights") or {}
    cid = candidate.get("channelId")
    if cid and cid in weights:
        return min(1.0, weights[cid])
    if candidate.get("source") in ("subscription_feed", "notification"):
        return 0.85
    return 0.0


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
    tag_overlap = min(1.0, tag_overlap + _interest_terms_in_title(profile, candidate.get("title", "")))

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
        top_weights = {
            (e.get("artist") or "").lower(): e.get("weight", 0)
            for e in profile.get("top_artists", [])
        }
        artist_fit = 0.35 + min(0.65, top_weights.get(channel, 0) * 2)

    source = candidate.get("source", "")
    if source in _HIGH_TRUST:
        source_fit = 1.0
    elif source == TOP_ARTIST_EXPLORE_SUFFIX_SOURCE:
        source_fit = 0.92
    elif source == YT_EXPLORE_SOURCE or source == "gemini_query":
        source_fit = 0.65
    elif source.startswith("oauth_"):
        source_fit = 0.95
    else:
        source_fit = 0.55

    views = int(candidate.get("viewCount") or 0)
    engagement = _log_views(views)
    like_ratio = float(candidate.get("likeRatio") or 0)
    if like_ratio > 0:
        engagement = min(1.0, engagement * 0.7 + min(1.0, like_ratio * 1000) * 0.3)

    recency = _recency_score(candidate.get("publishedAt", ""), profile)
    behavioral = _behavioral_affinity(candidate, profile)
    sub_boost = _subscription_boost(candidate, profile)
    penalty = _negative_penalty(candidate, profile)

    freshness = 0.5
    pub = candidate.get("publishedAt") or ""
    if pub:
        try:
            year = int(pub[:4])
            if year >= 2023:
                freshness = 0.9
            elif year >= 2018:
                freshness = 0.7
        except (ValueError, TypeError):
            pass

    music_boost = float(candidate.get("musicScore") or 0) * 12.0
    if candidate.get("categoryId") == "10":
        music_boost = max(music_boost, 8.0)

    lib_artist_names = {
        (e.get("artist") or "").lower()
        for e in profile.get("top_artists", [])
        if e.get("from_library")
    }
    if channel in lib_artist_names or focus in lib_artist_names:
        artist_fit = min(1.0, artist_fit + 0.25)

    raw = (
        tag_overlap * 22.0
        + artist_fit * 22.0
        + behavioral * 18.0
        + source_fit * 10.0
        + engagement * 8.0
        + recency * 8.0
        + sub_boost * 5.0
        + freshness * 5.0
        + music_boost
        - penalty * 15.0
    )
    return round(max(0.0, min(100.0, raw)), 2)


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
