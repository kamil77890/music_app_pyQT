import re
from difflib import SequenceMatcher


def normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\(.*?\)", "", text)
    text = re.sub(r"\[.*?\]", "", text)
    text = re.sub(r"official|video|lyrics|hd|4k|audio", "", text)
    text = re.sub(r"[^a-z0-9\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def is_duplicate(new_title, new_artist, library, threshold=0.88):
    """
    Checks if song already exists in library using fuzzy + normalized matching.
    """
    new_key = normalize(f"{new_title} {new_artist}")

    for s in library:
        existing_key = normalize(f"{s.get('title','')} {s.get('artist','')}")

        if similarity(new_key, existing_key) >= threshold:
            return True

    return False


def filter_duplicates(recommendations, library):
    """
    Removes duplicates + near-duplicates from Gemini output.
    """
    cleaned = []
    seen = set()

    for rec in recommendations:
        title = rec.get("title", "")
        artist = rec.get("artist", "")

        key = normalize(f"{title} {artist}")

        if key in seen:
            continue

        if is_duplicate(title, artist, library):
            continue

        seen.add(key)
        cleaned.append(rec)

    return cleaned