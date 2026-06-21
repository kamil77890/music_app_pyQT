from __future__ import annotations

import ast
import json
import re
from typing import Any

from app.logic.local_ai.metadata_normalizer import UNKNOWN_GENRE, is_garbage_genre, normalize_genre

_BROAD_GENRES = frozenset(
    {
        "rock",
        "pop",
        "electronic",
        "soundtrack",
        "classical",
        "hip hop",
        "metal",
        "jazz",
        "folk",
        "ambient",
        "dance",
        "orchestral",
        "country",
        "blues",
        "reggae",
        "soul",
        "funk",
        "r&b",
        "indie",
        "alternative",
        "latin",
        "world",
        "punk",
        "disco",
        "house",
        "techno",
        "trance",
        "gospel",
        "unknown genre",
    }
)

_GENRE_ALIASES = {
    "electro pop": "Electronic",
    "electronic pop": "Electronic",
    "edm": "Electronic",
    "lofi": "Electronic",
    "lo-fi": "Electronic",
}

_CONTEXT_LABELS = frozenset(
    {
        "anime",
        "cyberpunk",
        "game",
        "movie",
        "youtube",
        "tiktok",
        "lyrics",
        "manga",
        "tv",
        "series",
        "film",
        "videogame",
        "meme",
        "vtuber",
        "op",
        "ed",
        "opening",
        "ending",
        "lyric video",
        "lyrics video",
    }
)

_STYLE_LABELS = frozenset(
    {
        "piano",
        "cover",
        "remix",
        "nightcore",
        "instrumental",
        "jumpstyle",
        "acoustic",
        "karaoke",
        "live",
        "vocal",
        "sped up",
        "slowed",
        "lo-fi",
        "lofi",
        "orchestral",
        "arrangement",
        "hardstyle",
        "dubstep",
        "synthwave",
    }
)

_USEFUL_TAG_WORDS = frozenset(
    {
        "rock",
        "pop",
        "piano",
        "nightcore",
        "electronic",
        "lyrics",
        "ost",
        "soundtrack",
        "instrumental",
        "cover",
        "remix",
        "dance",
        "jumpstyle",
        "ambient",
        "orchestral",
        "classical",
        "metal",
        "hip",
        "hop",
        "anime",
        "cyberpunk",
        "opening",
        "ending",
        "op",
        "ed",
        "game",
        "movie",
        "tv",
        "film",
        "acoustic",
        "vocal",
        "hardstyle",
        "dubstep",
        "synthwave",
        "retro-futuristic",
        "retro",
        "futuristic",
    }
)

_WEAK_TAGS = frozenset(
    {
        "young",
        "punk",
        "harder",
        "different",
        "version",
        "song",
        "single",
        "edit",
        "mix",
        "audio",
        "video",
        "music",
        "track",
        "original",
        "official",
        "full",
        "hd",
        "4k",
        "hits",
        "hit",
        "but",
        "it",
        "the",
        "a",
        "an",
        "and",
        "or",
        "with",
        "from",
        "by",
        "clearly",
        "likely",
        "probably",
    }
)

_TAG_NORMALIZATIONS: tuple[tuple[str, str, str | None], ...] = (
    ("rock version", "Rock", None),
    ("piano version", "Piano", "Piano"),
    ("lyric video", "Lyrics", None),
    ("lyrics video", "Lyrics", None),
    ("original soundtrack", "OST", None),
    ("lyric", "Lyrics", None),
    ("nightcore", "Nightcore", "Nightcore"),
    ("jumpstyle", "Jumpstyle", "Jumpstyle"),
    ("lyrics", "Lyrics", None),
    ("cover", "Cover", "Cover"),
    ("remix", "Remix", "Remix"),
    ("instrumental", "Instrumental", "Instrumental"),
    ("piano", "Piano", "Piano"),
    ("rock", "Rock", None),
    ("dance", "Dance", None),
    ("electronic", "Electronic", None),
)

_GENERIC_GENRE_LABELS = frozenset(
    {
        "music",
        "general music",
        "song",
        "songs",
        "audio",
        "video",
        "musik",
        "track",
        "tracks",
    }
)

_CONFIDENT_BROAD_GENRES = frozenset(
    {
        "rock",
        "pop",
        "electronic",
        "dance",
        "soundtrack",
        "classical",
        "hip hop",
        "metal",
        "jazz",
        "folk",
        "ambient",
        "orchestral",
    }
)

_SOUNDTRACK_MARKERS = re.compile(
    r"\b(ost|soundtrack|opening|ending|theme|score)\b|\bop\b|\bed\b",
    re.IGNORECASE,
)
_SOUNDTRACK_PROOF_MARKERS = re.compile(
    r"\b(ost|soundtrack|opening|ending|score|episode|series)\b|\bop\b|\bed\b|\b(movie|film|anime|game)\b",
    re.IGNORECASE,
)
_ROCK_VERSION_MARKER = re.compile(r"\brock version\b", re.IGNORECASE)
_PIANO_MARKER = re.compile(r"\b(piano|piano version|piano cover|piano arrangement|arr\.?)\b", re.IGNORECASE)
_NIGHTCORE_MARKER = re.compile(r"\bnightcore\b", re.IGNORECASE)
_LYRICS_MARKER = re.compile(r"\b(lyrics|lyric|lyric video|lyrics video)\b", re.IGNORECASE)
_INSTRUMENTAL_MARKER = re.compile(r"\b(instrumental|no vocals|without vocals|karaoke)\b", re.IGNORECASE)
_JUMPSTYLE_MARKER = re.compile(r"\bjumpstyle\b", re.IGNORECASE)
_DANCE_MARKER = re.compile(r"\b(jumpstyle|dance|edm)\b", re.IGNORECASE)
_REMIX_COVER_MARKER = re.compile(r"\b(remix|cover|version|arrangement|arr\.?)\b", re.IGNORECASE)
_CLASSICAL_MARKER = re.compile(r"\b(beethoven|sonata|symphony|concerto|classical|moonlight sonata)\b", re.IGNORECASE)
_GAME_MARKER = re.compile(r"\b(game|video game|game soundtrack)\b", re.IGNORECASE)
_MOVIE_MARKER = re.compile(r"\b(movie|film)\b", re.IGNORECASE)
_ANIME_MARKER = re.compile(r"\b(anime|op|ed|opening|ending|ost|soundtrack)\b", re.IGNORECASE)

_MAX_REASON_LEN = 160
_REASON_CLAIM_MARKERS = re.compile(
    r"\b(manga|manhwa|light novel|tv series|video game franchise|game soundtrack|anime series|movie soundtrack)\b",
    re.IGNORECASE,
)
_OVERCONFIDENT_REASON = re.compile(r"\bclearly\b", re.IGNORECASE)

_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "by",
        "with",
        "from",
        "it",
        "is",
        "are",
        "was",
        "were",
        "this",
        "that",
        "but",
        "hits",
        "hit",
        "different",
        "harder",
        "version",
        "lyrics",
        "lyric",
        "video",
        "audio",
        "official",
        "hd",
        "arr",
        "arrangement",
    }
)


def _normalize_key(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _title_case_tag(value: str) -> str:
    text = re.sub(r"\s+", " ", value.strip())
    if not text:
        return ""
    if text.isupper() and len(text) <= 4:
        return text
    return " ".join(part.capitalize() if part.lower() not in {"and", "&", "of"} else part for part in text.split())


def _trusted_existing_genre(track: dict[str, Any] | None) -> str:
    if not track:
        return ""
    raw = track.get("existing_genre") or track.get("genre") or ""
    normalized = normalize_genre(raw)
    if normalized == UNKNOWN_GENRE or is_garbage_genre(raw):
        return ""
    if is_context_label(normalized) or is_style_label(normalized):
        return ""
    if not is_broad_genre(normalized):
        return ""
    return normalized


def _track_proof_haystack(track: dict[str, Any] | None) -> str:
    if not track:
        return ""
    parts = [
        str(track.get(key) or "")
        for key in ("title", "artist", "album", "source_title", "sourceTitle", "description")
    ]
    trusted_genre = _trusted_existing_genre(track)
    if trusted_genre:
        parts.append(trusted_genre)
    return " ".join(parts)


def _track_input_haystack(track: dict[str, Any] | None) -> str:
    return _track_proof_haystack(track)


def _input_haystack(track: dict[str, Any] | None, *, parsed: dict[str, Any] | None = None) -> str:
    parts = [_track_input_haystack(track)]
    if parsed:
        parts.extend(
            str(parsed.get(key) or "")
            for key in ("genre", "primary_genre", "style", "subgenre", "collection")
        )
        parts.append(" ".join(str(tag) for tag in (parsed.get("tags") or [])))
    return " ".join(parts)


def _tokenize_words(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9']+", _normalize_key(text)) if token}


def _tag_is_artist_leakage(tag: str, track: dict[str, Any] | None) -> bool:
    if not track:
        return False
    tag_norm = _normalize_key(tag)
    if not tag_norm:
        return False
    artist_norm = _normalize_key(track.get("artist"))
    if artist_norm and (tag_norm == artist_norm or tag_norm in artist_norm.split()):
        return tag_norm not in _USEFUL_TAG_WORDS
    for key in ("title", "source_title", "sourceTitle", "description"):
        text = str(track.get(key) or "")
        by_match = re.search(r"\bby\s+([^(\[\]-]+)", text, flags=re.IGNORECASE)
        if by_match and tag_norm in _normalize_key(by_match.group(1)):
            return True
    return False


def _tag_is_title_leakage(tag: str, track: dict[str, Any] | None) -> bool:
    if not track:
        return False
    tag_norm = _normalize_key(tag)
    if not tag_norm or tag_norm in _USEFUL_TAG_WORDS:
        return False
    title_norm = _normalize_key(track.get("title"))
    if not title_norm:
        return False
    if tag_norm in title_norm and len(tag_norm) >= 4:
        return True
    title_tokens = _tokenize_words(title_norm)
    tag_tokens = _tokenize_words(tag_norm)
    if not tag_tokens:
        return False
    if len(tag_tokens) == 1 and tag_tokens.pop() in title_tokens and tag_norm not in _USEFUL_TAG_WORDS:
        return True
    return False


def _tag_is_grounded(
    tag: str,
    *,
    track_haystack: str,
    genre: str,
    primary_genre: str,
    style: str | None,
) -> bool:
    tag_norm = _normalize_key(tag)
    haystack_norm = _normalize_key(track_haystack)
    genre_norm = _normalize_key(genre)
    primary_norm = _normalize_key(primary_genre)
    style_norm = _normalize_key(style) if style else ""
    style_is_grounded = bool(style_norm and _style_is_grounded(style, track_haystack))

    if not tag_norm:
        return False

    if tag_norm in {genre_norm, primary_norm} and is_broad_genre(tag) and tag != UNKNOWN_GENRE:
        return True
    if style_is_grounded and tag_norm == style_norm:
        return True

    if tag_norm == "piano":
        return bool(_PIANO_MARKER.search(haystack_norm)) or (style_is_grounded and style_norm == "piano")
    if tag_norm == "lyrics":
        return bool(_LYRICS_MARKER.search(haystack_norm))
    if tag_norm == "jumpstyle":
        return bool(_JUMPSTYLE_MARKER.search(haystack_norm)) or (style_is_grounded and style_norm == "jumpstyle")
    if tag_norm == "nightcore":
        return bool(_NIGHTCORE_MARKER.search(haystack_norm)) or (style_is_grounded and style_norm == "nightcore")
    if tag_norm == "rock":
        return (
            bool(re.search(r"\brock\b", haystack_norm))
            or genre_norm == "rock"
            or primary_norm == "rock"
            or bool(_ROCK_VERSION_MARKER.search(haystack_norm))
        )
    if tag_norm == "pop":
        return genre_norm == "pop" or primary_norm == "pop" or "pop" in haystack_norm
    if tag_norm == "electronic":
        return genre_norm == "electronic" or primary_norm == "electronic" or "electronic" in haystack_norm
    if tag_norm == "dance":
        return genre_norm == "dance" or primary_norm == "dance" or bool(_DANCE_MARKER.search(haystack_norm))
    if tag_norm in {"ost", "soundtrack"}:
        return bool(_SOUNDTRACK_PROOF_MARKERS.search(haystack_norm)) or (
            genre_norm == "soundtrack"
            and primary_norm == "soundtrack"
            and bool(_SOUNDTRACK_PROOF_MARKERS.search(haystack_norm))
        )
    if tag_norm == "game":
        return bool(_GAME_MARKER.search(haystack_norm))
    if tag_norm in {"movie", "film"}:
        return bool(_MOVIE_MARKER.search(haystack_norm))
    if tag_norm == "anime":
        return bool(_ANIME_MARKER.search(haystack_norm))
    if tag_norm == "cover":
        return bool(re.search(r"\bcover\b", haystack_norm)) or (style_is_grounded and style_norm == "cover")
    if tag_norm == "remix":
        return bool(re.search(r"\bremix\b", haystack_norm)) or (style_is_grounded and style_norm == "remix")
    if tag_norm == "instrumental":
        return bool(_INSTRUMENTAL_MARKER.search(haystack_norm)) or (style_is_grounded and style_norm == "instrumental")
    if tag_norm == "classical":
        return bool(_CLASSICAL_MARKER.search(haystack_norm)) or genre_norm == "classical"
    if tag_norm in {"opening", "ending", "op", "ed"}:
        return bool(_SOUNDTRACK_MARKERS.search(haystack_norm))
    if tag_norm in _USEFUL_TAG_WORDS:
        return tag_norm in haystack_norm
    return tag_norm in haystack_norm


def _style_is_grounded(style: str | None, track_haystack: str) -> bool:
    if not style:
        return True
    norm = _normalize_key(style)
    haystack = _normalize_key(track_haystack)
    if norm == "piano":
        return bool(_PIANO_MARKER.search(haystack))
    if norm == "nightcore":
        return bool(_NIGHTCORE_MARKER.search(haystack))
    if norm in {"remix", "cover"}:
        return bool(_REMIX_COVER_MARKER.search(haystack))
    if norm == "jumpstyle":
        return bool(_JUMPSTYLE_MARKER.search(haystack))
    if is_style_label(style):
        return bool(_INSTRUMENTAL_MARKER.search(haystack)) if norm == "instrumental" else norm in haystack
    return True


def _tag_supported_by_input(tag: str, input_haystack: str) -> bool:
    tag_norm = _normalize_key(tag)
    haystack_norm = _normalize_key(input_haystack)
    if tag_norm == "game":
        return bool(_GAME_MARKER.search(haystack_norm))
    if tag_norm == "movie" or tag_norm == "film":
        return bool(_MOVIE_MARKER.search(haystack_norm))
    if tag_norm == "anime":
        return bool(_ANIME_MARKER.search(haystack_norm))
    return True


def is_context_label(value: Any) -> bool:
    norm = _normalize_key(value)
    if not norm:
        return False
    if norm in _CONTEXT_LABELS:
        return True
    tokens = set(norm.replace("/", " ").replace("-", " ").split())
    return bool(tokens & _CONTEXT_LABELS)


def is_style_label(value: Any) -> bool:
    norm = _normalize_key(value)
    if not norm:
        return False
    if norm in _STYLE_LABELS:
        return True
    tokens = set(norm.replace("/", " ").replace("-", " ").split())
    return len(tokens) == 1 and bool(tokens & _STYLE_LABELS)


def is_generic_genre_label(value: Any) -> bool:
    return _normalize_key(value) in _GENERIC_GENRE_LABELS


def is_broad_genre(value: Any) -> bool:
    norm = _normalize_key(normalize_genre(value))
    if norm in _GENRE_ALIASES:
        norm = _normalize_key(_GENRE_ALIASES[norm])
    if norm == _normalize_key(UNKNOWN_GENRE):
        return False
    if is_generic_genre_label(norm):
        return False
    if is_context_label(norm) or is_style_label(norm):
        return False
    if norm in _BROAD_GENRES:
        return True
    return not is_garbage_genre(value) and len(norm.split()) <= 3


def _normalize_generic_genre_fields(genre: str, primary_genre: str) -> tuple[str, str, bool]:
    changed = False
    genre_generic = is_generic_genre_label(genre)
    primary_generic = is_generic_genre_label(primary_genre)
    genre_valid = is_broad_genre(genre) and genre != UNKNOWN_GENRE and not genre_generic
    primary_valid = is_broad_genre(primary_genre) and primary_genre != UNKNOWN_GENRE and not primary_generic

    if genre_generic and primary_generic:
        return UNKNOWN_GENRE, UNKNOWN_GENRE, True
    if genre_generic and primary_valid:
        return primary_genre, primary_genre, True
    if primary_generic and genre_valid:
        return genre, genre, True
    if genre_generic:
        changed = True
        genre = UNKNOWN_GENRE
    if primary_generic:
        changed = True
        primary_genre = UNKNOWN_GENRE
    if genre == UNKNOWN_GENRE and primary_valid:
        genre = primary_genre
        changed = True
    if primary_genre == UNKNOWN_GENRE and genre_valid:
        primary_genre = genre
        changed = True
    return genre, primary_genre, changed


def _track_has_soundtrack_proof(track: dict[str, Any] | None, *, track_haystack: str | None = None) -> bool:
    haystack = track_haystack if track_haystack is not None else _track_proof_haystack(track)
    return bool(_SOUNDTRACK_PROOF_MARKERS.search(_normalize_key(haystack)))


def _enforce_soundtrack_genre_proof(
    *,
    genre: str,
    primary_genre: str,
    tags: list[str],
    track_haystack: str,
) -> tuple[str, str, list[str], bool]:
    if _normalize_key(genre) != "soundtrack" and _normalize_key(primary_genre) != "soundtrack":
        return genre, primary_genre, tags, False
    if _SOUNDTRACK_PROOF_MARKERS.search(_normalize_key(track_haystack)):
        return genre, primary_genre, tags, False
    cleaned_tags = [tag for tag in tags if _normalize_key(tag) != "soundtrack"]
    return UNKNOWN_GENRE, UNKNOWN_GENRE, cleaned_tags, True


def _normalize_broad_genre(value: Any) -> str:
    norm = _normalize_key(normalize_genre(value))
    if norm in _GENRE_ALIASES:
        return _GENRE_ALIASES[norm]
    return normalize_genre(value)


def _model_output_suggests_soundtrack(parsed: dict[str, Any]) -> bool:
    parts = [
        parsed.get("subgenre"),
        parsed.get("style"),
        parsed.get("collection"),
        " ".join(parsed.get("tags") or []),
        " ".join(parsed.get("mood") or []),
    ]
    text = f" {' '.join(str(part) for part in parts if part)} "
    return bool(_SOUNDTRACK_MARKERS.search(text))


def _track_suggests_soundtrack(track: dict[str, Any] | None) -> bool:
    return _track_has_soundtrack_proof(track)


def _suggests_soundtrack(parsed: dict[str, Any], track: dict[str, Any] | None) -> bool:
    return _track_has_soundtrack_proof(track)


def _sanitize_reason(reason: str, track: dict[str, Any] | None, *, sanitized: bool = False) -> tuple[str, bool]:
    text = re.sub(r"\s+", " ", str(reason or "").strip())
    if not text:
        return "Classified from available metadata.", sanitized
    changed = False
    if _OVERCONFIDENT_REASON.search(text):
        text = _OVERCONFIDENT_REASON.sub("", text).strip()
        changed = True
    if track and _REASON_CLAIM_MARKERS.search(text):
        haystack = _normalize_key(_track_input_haystack(track))
        claim = _REASON_CLAIM_MARKERS.search(text)
        if claim and _normalize_key(claim.group(0)) not in haystack:
            return "Classified from available metadata labels.", True
    if len(text) > _MAX_REASON_LEN:
        text = text[: _MAX_REASON_LEN - 3].rstrip() + "..."
        changed = True
    if changed:
        sanitized = True
    return text or "Classified from available metadata.", sanitized


def _normalize_tag_candidate(tag: str, *, style: str | None) -> tuple[str | None, str | None]:
    text = _title_case_tag(tag)
    if not text:
        return None, style
    norm = _normalize_key(text)
    if norm in _WEAK_TAGS or is_garbage_genre(text):
        return None, style
    for pattern, normalized_tag, style_hint in _TAG_NORMALIZATIONS:
        if pattern in norm:
            updated_style = style
            if style_hint and not updated_style:
                updated_style = style_hint
            return normalized_tag, updated_style
    if is_context_label(text) or is_style_label(text):
        updated_style = style or (text if is_style_label(text) else style)
        return text, updated_style
    return text, style


def _clean_tags(
    tags: list[str],
    *,
    track: dict[str, Any] | None,
    style: str | None,
    track_haystack: str,
    genre: str,
    primary_genre: str,
) -> tuple[list[str], str | None, int, int]:
    seen: set[str] = set()
    cleaned: list[str] = []
    current_style = style
    removed = 0
    unsupported_removed = 0
    for tag in tags:
        text, current_style = _normalize_tag_candidate(tag, style=current_style)
        if not text:
            removed += 1
            continue
        if _tag_is_artist_leakage(text, track) or _tag_is_title_leakage(text, track):
            removed += 1
            continue
        if not _tag_supported_by_input(text, track_haystack):
            unsupported_removed += 1
            removed += 1
            continue
        if _normalize_key(text) == "classical" and not _CLASSICAL_MARKER.search(track_haystack):
            unsupported_removed += 1
            removed += 1
            continue
        if not _tag_is_grounded(
            text,
            track_haystack=track_haystack,
            genre=genre,
            primary_genre=primary_genre,
            style=current_style,
        ):
            unsupported_removed += 1
            removed += 1
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned, current_style, removed, unsupported_removed


def _relocate_label(label: str, *, tags: list[str], style: str | None, collection: str | None) -> tuple[str | None, str | None]:
    tag_text = _title_case_tag(label)
    norm = _normalize_key(tag_text)
    if is_context_label(norm):
        if not collection:
            collection = tag_text
        if tag_text.lower() not in {t.lower() for t in tags}:
            tags.append(tag_text)
        return style, collection
    if is_style_label(norm):
        if not style:
            style = tag_text
        if tag_text.lower() not in {t.lower() for t in tags}:
            tags.append(tag_text)
        return style, collection
    if tag_text.lower() not in {t.lower() for t in tags}:
        tags.append(tag_text)
    return style, collection


def _coerce_field_value(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return list(value)
    if not isinstance(value, str):
        return value
    text = value.strip()
    if text.startswith("[") and text.endswith("]"):
        try:
            return json.loads(text.replace("'", '"'))
        except json.JSONDecodeError:
            try:
                parsed = ast.literal_eval(text)
                return parsed if isinstance(parsed, list) else value
            except (ValueError, SyntaxError):
                return value
    return value


def _coerce_optional_text(value: Any) -> str | None:
    coerced = _coerce_field_value(value)
    if isinstance(coerced, list):
        parts = [_title_case_tag(str(item)) for item in coerced if str(item).strip()]
        parts = [part for part in parts if part]
        return ", ".join(parts) if parts else None
    text = re.sub(r"\s+", " ", str(coerced or "").strip())
    return text or None


def _coerce_collection(value: Any, tags: list[str]) -> str | None:
    coerced = _coerce_field_value(value)
    if isinstance(coerced, list):
        collection: str | None = None
        for item in coerced:
            text = _title_case_tag(str(item))
            if not text:
                continue
            if is_context_label(text) and collection is None:
                collection = text
            elif text.lower() not in {t.lower() for t in tags}:
                tags.append(text)
        return collection
    text = re.sub(r"\s+", " ", str(coerced or "").strip())
    return text or None


def _recalculate_confidence(
    *,
    genre: str,
    style: str | None,
    tags: list[str],
    track: dict[str, Any] | None,
    genre_fixed: bool,
    tags_removed: int,
    unsupported_tags_removed: int,
    reason_sanitized: bool,
    serious_validator_problem: bool = False,
) -> float:
    score = 0.0
    if is_broad_genre(genre) and genre != UNKNOWN_GENRE:
        score += 0.25
    if style:
        score += 0.20
    if tags:
        score += 0.15
    if track and str(track.get("title") or "").strip() and str(track.get("artist") or "").strip():
        score += 0.10
    if genre_fixed:
        score -= 0.15
    if unsupported_tags_removed > 0:
        score -= 0.15
    if tags_removed >= 2:
        score -= 0.10
    if reason_sanitized:
        score -= 0.10
    score = max(0.0, min(round(score, 2), 0.95))
    if genre == UNKNOWN_GENRE:
        score = min(score, 0.45)
    if genre == UNKNOWN_GENRE and style:
        score = min(score, 0.55)
    if len(tags) <= 1 and genre == UNKNOWN_GENRE:
        score = min(score, 0.55)
    genre_norm = _normalize_key(genre)
    if (
        not serious_validator_problem
        and genre != UNKNOWN_GENRE
        and is_broad_genre(genre)
        and genre_norm in _CONFIDENT_BROAD_GENRES
    ):
        score = max(score, 0.25)
    return score


def _apply_consistency_fixes(
    *,
    genre: str,
    primary_genre: str,
    style: str | None,
    tags: list[str],
    track: dict[str, Any] | None,
    parsed: dict[str, Any],
    track_haystack: str,
    input_haystack: str,
) -> tuple[str, str, str | None, list[str], str | None]:
    reason_hint: str | None = None
    tag_blob = " ".join(tags).lower()
    style_norm = _normalize_key(style)

    if _ROCK_VERSION_MARKER.search(track_haystack):
        genre = primary_genre = "Rock"
        if "Rock" not in tags:
            tags.append("Rock")
        reason_hint = "Rock Version appears in metadata; broad genre set to Rock."

    if _normalize_key(genre) == "classical" and not _CLASSICAL_MARKER.search(track_haystack):
        genre = primary_genre = UNKNOWN_GENRE
        reason_hint = "Classical genre removed because input lacks classical markers."

    if style_norm == "nightcore" and genre == UNKNOWN_GENRE:
        if "jumpstyle" in tag_blob or "dance" in tag_blob:
            genre = primary_genre = "Dance"
            reason_hint = "Nightcore style detected; broad genre set to Dance."
        else:
            genre = primary_genre = "Electronic"
            reason_hint = "Nightcore style detected; broad genre set to Electronic."

    if "jumpstyle" in tag_blob and genre == UNKNOWN_GENRE:
        genre = primary_genre = "Dance"
        reason_hint = "Jumpstyle tag detected; broad genre set to Dance."

    if style_norm == "piano" and _track_has_soundtrack_proof(track, track_haystack=track_haystack):
        genre = primary_genre = "Soundtrack"
        reason_hint = "Piano arrangement of media/OST track; broad genre set to Soundtrack."

    if _CLASSICAL_MARKER.search(track_haystack) and genre == UNKNOWN_GENRE:
        genre = primary_genre = "Classical"
        reason_hint = "Classical markers detected in metadata; broad genre set to Classical."

    if _normalize_key(primary_genre) == "hip hop" and ("jumpstyle" in tag_blob or style_norm == "jumpstyle"):
        genre = primary_genre = "Dance"
        reason_hint = "Jumpstyle style detected; broad genre set to Dance."

    return genre, primary_genre, style, tags, reason_hint


def validate_model_classification(parsed: dict[str, Any], *, track: dict[str, Any] | None = None) -> dict[str, Any]:
    tags = [str(item).strip() for item in (parsed.get("tags") or []) if str(item).strip()]
    genre = _normalize_broad_genre(parsed.get("genre"))
    primary_genre = _normalize_broad_genre(parsed.get("primary_genre") or parsed.get("genre"))
    style = _coerce_optional_text(parsed.get("style"))
    subgenre = _coerce_optional_text(parsed.get("subgenre"))
    collection = _coerce_collection(parsed.get("collection"), tags)
    mood = [str(item).strip() for item in (parsed.get("mood") or []) if str(item).strip()]
    track_haystack = _track_input_haystack(track)
    input_haystack = _input_haystack(track, parsed=parsed)
    genre_fixed = False
    original_tag_count = len(tags)
    unsupported_removed = 0

    for candidate in (genre, primary_genre):
        if is_garbage_genre(candidate):
            genre = UNKNOWN_GENRE
            primary_genre = UNKNOWN_GENRE
            genre_fixed = True
            break

    def fix_genre_field(value: str) -> str:
        nonlocal style, collection, tags, genre_fixed
        if is_garbage_genre(value) or not value or value == UNKNOWN_GENRE:
            genre_fixed = True
            return UNKNOWN_GENRE
        if is_context_label(value) or is_style_label(value) or not is_broad_genre(value):
            style, collection = _relocate_label(value, tags=tags, style=style, collection=collection)
            genre_fixed = True
            if _suggests_soundtrack(parsed, track):
                return "Soundtrack"
            return UNKNOWN_GENRE
        return _normalize_broad_genre(value)

    genre = fix_genre_field(genre)
    primary_genre = fix_genre_field(primary_genre)

    genre, primary_genre, generic_fixed = _normalize_generic_genre_fields(genre, primary_genre)
    if generic_fixed:
        genre_fixed = True

    if subgenre:
        if (
            is_context_label(subgenre)
            or is_style_label(subgenre)
            or is_garbage_genre(subgenre)
            or _normalize_key(subgenre) in {"op", "ed", "opening", "ending", "lyrics", "lyric video", "lyrics video"}
        ):
            style, collection = _relocate_label(subgenre, tags=tags, style=style, collection=collection)
            subgenre = None
            genre_fixed = True

    if style and (is_garbage_genre(style) or is_context_label(style)):
        style, collection = _relocate_label(style, tags=tags, style=None, collection=collection)
        genre_fixed = True

    if collection:
        if is_garbage_genre(collection) or is_style_label(collection):
            style, collection = _relocate_label(collection, tags=tags, style=style, collection=None)
            genre_fixed = True
        elif not _tag_supported_by_input(collection, track_haystack):
            collection = None
            genre_fixed = True
        elif track and _normalize_key(collection) == _normalize_key(track.get("artist")):
            collection = None
            genre_fixed = True

    if genre == UNKNOWN_GENRE and primary_genre != UNKNOWN_GENRE:
        genre = primary_genre
    if primary_genre == UNKNOWN_GENRE and genre != UNKNOWN_GENRE:
        primary_genre = genre
    if genre == UNKNOWN_GENRE and primary_genre == UNKNOWN_GENRE and _track_has_soundtrack_proof(track, track_haystack=track_haystack):
        genre = primary_genre = "Soundtrack"
        genre_fixed = True
    if _normalize_key(primary_genre) == "soundtrack" and genre not in {UNKNOWN_GENRE, "Soundtrack"}:
        if _track_has_soundtrack_proof(track, track_haystack=track_haystack):
            genre = "Soundtrack"
            genre_fixed = True
        else:
            primary_genre = genre
            genre_fixed = True

    tags, updated_style, tags_removed, unsupported_removed = _clean_tags(
        tags,
        track=track,
        style=style,
        track_haystack=track_haystack,
        genre=genre,
        primary_genre=primary_genre,
    )
    if updated_style and not style:
        style = updated_style
    tags_removed += max(0, original_tag_count - len(tags))

    genre, primary_genre, style, tags, reason_hint = _apply_consistency_fixes(
        genre=genre,
        primary_genre=primary_genre,
        style=style,
        tags=tags,
        track=track,
        parsed=parsed,
        track_haystack=track_haystack,
        input_haystack=input_haystack,
    )

    if style and not _style_is_grounded(style, track_haystack):
        style = None
        genre_fixed = True

    tags, _, final_removed, final_unsupported = _clean_tags(
        tags,
        track=track,
        style=style,
        track_haystack=track_haystack,
        genre=genre,
        primary_genre=primary_genre,
    )
    tags_removed += final_removed
    unsupported_removed += final_unsupported

    if style and _style_is_grounded(style, track_haystack):
        style_tag = _title_case_tag(style)
        if style_tag and style_tag.lower() not in {tag.lower() for tag in tags}:
            if _tag_is_grounded(
                style_tag,
                track_haystack=track_haystack,
                genre=genre,
                primary_genre=primary_genre,
                style=style,
            ):
                tags.append(style_tag)

    serious_validator_problem = False
    genre, primary_genre, tags, soundtrack_rejected = _enforce_soundtrack_genre_proof(
        genre=genre,
        primary_genre=primary_genre,
        tags=tags,
        track_haystack=track_haystack,
    )
    if soundtrack_rejected:
        genre_fixed = True
        serious_validator_problem = True

    reason, reason_sanitized = _sanitize_reason(str(parsed.get("reason") or ""), track)
    if reason_hint:
        reason = reason_hint
    elif genre_fixed and reason == "Classified from available metadata.":
        reason = "Adjusted model output to use broad music genres and cleaned tags."

    confidence = _recalculate_confidence(
        genre=genre,
        style=style,
        tags=tags,
        track=track,
        genre_fixed=genre_fixed,
        tags_removed=tags_removed,
        unsupported_tags_removed=unsupported_removed,
        reason_sanitized=reason_sanitized,
        serious_validator_problem=serious_validator_problem,
    )

    metadata_quality = str(parsed.get("metadata_quality") or "low").lower()
    if metadata_quality not in {"low", "medium", "high"}:
        metadata_quality = "low"

    return {
        "genre": genre,
        "primary_genre": primary_genre,
        "style": style,
        "subgenre": subgenre,
        "collection": collection,
        "mood": mood,
        "tags": tags,
        "metadata_quality": metadata_quality,
        "classification_confidence": confidence,
        "reason": reason,
    }
