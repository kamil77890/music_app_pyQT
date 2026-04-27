import re
import json


def normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\(.*?\)", "", text)
    text = re.sub(r"\[.*?\]", "", text)
    text = re.sub(r"[^a-z0-9\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def compact_json(data) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def strip_cover_data(songs):
    return [{k: v for k, v in s.items() if k != "cover_base64"} for s in songs]


def build_library_index(songs):
    titles = set()
    video_ids = set()

    for s in songs:
        if t := s.get("title"):
            titles.add(normalize(t))

        vid = s.get("videoId") or s.get("id")
        if vid:
            video_ids.add(str(vid))

    return titles, video_ids


def extract_style_hint(songs):
    artists = [s.get("artist") for s in songs if s.get("artist")]

    return {
        "top_artists": list(set(artists))[:10],
        "sample_songs": [
            {"title": s.get("title"), "artist": s.get("artist")}
            for s in songs[:10]
        ]
    }