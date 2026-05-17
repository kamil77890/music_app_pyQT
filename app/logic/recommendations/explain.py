from __future__ import annotations

from typing import Any

from app.logic.recommendations.recommendation_scorer import score_candidate


def explain_recommendation(
    video_id: str,
    graph: dict[str, Any],
    library_songs: list[dict[str, Any]],
    candidate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Why a video would be recommended (debug / transparency)."""
    if not candidate:
        candidate = {"videoId": video_id, "title": "", "artist": ""}

    library_artists = {
        (s.get("artist") or "").strip().lower()
        for s in library_songs
        if s.get("artist")
    }
    score = score_candidate(candidate, graph, library_artists)

    reasons: list[str] = []
    if candidate.get("source"):
        reasons.append(f"Discovery source: {candidate['source']}")
    if candidate.get("reason"):
        reasons.append(candidate["reason"])

    tags = candidate.get("matchedTags") or []
    if tags:
        overlap = set(tags) & set(graph.get("tag_histogram", {}).keys())
        if overlap:
            reasons.append(f"Tag overlap: {', '.join(sorted(overlap)[:5])}")

    for a in graph.get("top_artists", [])[:5]:
        if (a.get("artist") or "").lower() == (candidate.get("artist") or "").lower():
            reasons.append(f"Matches top artist: {a['artist']}")
            break

    behavioral = graph.get("behavioral") or {}
    for v in behavioral.get("top_videos", []):
        if v.get("video_id") == video_id:
            reasons.append(
                f"Played {v.get('play_count', 0)}x, "
                f"listen ratio {v.get('avg_listen_ratio', 0)}"
            )
            break

    cid = candidate.get("channelId")
    if cid and cid in (graph.get("channel_weights") or {}):
        reasons.append("Subscribed or frequently played channel")

    return {
        "video_id": video_id,
        "score": score,
        "reasons": reasons or ["General taste match"],
        "exploration_budget": graph.get("exploration_budget"),
    }
