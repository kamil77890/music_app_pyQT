import asyncio
import yt_dlp

from app.utils.music_utils import song_key


_YTDLP_OPTS = {
    "quiet": True,
    "skip_download": True,
    "extract_flat": True,
}


def cover_url(video_id: str) -> str:
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"


def _resolve_sync(title, artist):
    query = f"{artist} {title}".strip()

    try:
        with yt_dlp.YoutubeDL(_YTDLP_OPTS) as ydl:
            data = ydl.extract_info(f"ytsearch1:{query}", download=False)
            entry = (data.get("entries") or [None])[0]

            if not entry:
                return None

            vid = entry.get("id")
            if not vid:
                return None

            return {
                "title": entry.get("title"),
                "artist": artist,
                "videoId": vid,
                "url": f"https://www.youtube.com/watch?v={vid}",
                "coverUrl": cover_url(vid),
            }

    except Exception:
        return None


async def resolve_many(recs, max_results, existing_keys, existing_ids):
    sem = asyncio.Semaphore(8)
    results = []

    async def task(rec):
        async with sem:
            return await asyncio.to_thread(
                _resolve_sync,
                rec.get("title", ""),
                rec.get("artist", "")
            )

    tasks = [asyncio.create_task(task(r)) for r in recs if isinstance(r, dict)]

    for t in asyncio.as_completed(tasks):
        song = await t
        if not song:
            continue
        vid = song.get("videoId")
        if vid and vid in existing_ids:
            continue
        key = song_key(song)
        if key and key in existing_keys:
            continue
        results.append(song)
        if len(results) >= max_results:
            break

    return results
