import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.db_controller import DbController
from app.logic.lyrics import read_lyrics, save_lyrics

router = APIRouter(prefix="/api/lyrics", tags=["lyrics"])


class LyricsPayload(BaseModel):
    text: str = Field(..., min_length=1)
    format: str = Field("txt", pattern="^(txt|lrc)$")
    songId: int | None = None
    videoId: str | None = None
    title: str | None = None
    artist: str | None = None
    path: str | None = None


def _song_identity_from_payload(payload: LyricsPayload) -> dict | str:
    if payload.videoId:
        return {"videoId": payload.videoId}
    if payload.title or payload.artist or payload.path:
        return {
            "title": payload.title,
            "artist": payload.artist,
            "path": payload.path,
        }
    if payload.songId is not None:
        return str(payload.songId)
    return {
        "title": payload.title,
        "artist": payload.artist,
        "path": payload.path,
    }


def _update_lyrics_columns(payload: LyricsPayload, lyrics_path: str, text: str) -> None:
    db = DbController()
    try:
        lyrics_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        updated_at = datetime.now(timezone.utc).isoformat()
        params = [lyrics_path, lyrics_hash, updated_at, 1]

        if payload.songId is not None:
            db.execute_write(
                """
                UPDATE songs
                SET lyrics_path = ?, lyrics_hash = ?, lyrics_updated_at = ?, has_lyrics = ?
                WHERE id = ?
                """,
                params + [payload.songId],
            )
        elif payload.videoId:
            db.execute_write(
                """
                UPDATE songs
                SET lyrics_path = ?, lyrics_hash = ?, lyrics_updated_at = ?, has_lyrics = ?
                WHERE videoId = ?
                """,
                params + [payload.videoId],
            )
        elif payload.title and payload.artist:
            db.execute_write(
                """
                UPDATE songs
                SET lyrics_path = ?, lyrics_hash = ?, lyrics_updated_at = ?, has_lyrics = ?
                WHERE lower(title) = lower(?) AND lower(artist) = lower(?)
                """,
                params + [payload.title, payload.artist],
            )
        db.commit()
    finally:
        db.close()


@router.get("")
def get_lyrics(
    songId: int | None = Query(None),
    videoId: str | None = Query(None),
    title: str | None = Query(None),
    artist: str | None = Query(None),
    path: str | None = Query(None),
    includeText: bool = Query(True),
):
    if videoId:
        song = {"videoId": videoId}
    elif title or artist or path:
        song = {"title": title, "artist": artist, "path": path}
    elif songId is not None:
        song = str(songId)
    else:
        song = {}
    data = read_lyrics(song, include_text=includeText)
    if not data.get("hasLyrics"):
        raise HTTPException(status_code=404, detail="Lyrics not found")
    return data


@router.post("")
def upsert_lyrics(payload: LyricsPayload):
    song = _song_identity_from_payload(payload)
    lyrics_path = save_lyrics(payload.text, song=song, ext=payload.format)
    _update_lyrics_columns(payload, str(lyrics_path), payload.text)
    return {
        "hasLyrics": True,
        "lyricsPath": str(lyrics_path),
        "lyricsFormat": lyrics_path.suffix.lstrip("."),
    }
