from app.logic.recommendations.gemini_service import ask_gemini
from app.logic.recommendations.resolver import resolve_many
from app.utils.music_utils import build_library_index, extract_style_hint


_CACHE = {"key": None, "result": None}


def _key(songs):
    return len(songs)


from app.logic.recommendations.deduper import filter_duplicates


async def run_pipeline(songs, max_results):
    existing_titles, existing_ids = build_library_index(songs)

    gemini = await ask_gemini(songs, existing_titles, max_results * 3)

    recs = gemini.get("recommendations", [])
    profile = gemini.get("profile", {})

    # 🔥 NEW DEDUP MODEL STEP
    recs = filter_duplicates(recs, songs)

    # trim after cleaning
    recs = recs[:max_results]

    resolved = await resolve_many(
        recs,
        max_results,
        existing_titles,
        existing_ids,
    )

    return profile, resolved