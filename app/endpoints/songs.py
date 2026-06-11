from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from app.config.stałe import Parameters
from app.logic.library_scanner import inject_lyrics_text, scan_music_files
import os

router = APIRouter(prefix="/api", tags=["songs"])


@router.get("/songs")
async def get_songs(includeLyrics: bool = Query(False, description="Include full lyrics text in each song")):
    try:
        download_dir = Parameters.get_download_dir()
        if not os.path.isdir(download_dir):
            return JSONResponse({"songs": [], "message": "Download directory not found"})

        songs = scan_music_files(download_dir)
        if includeLyrics:
            songs = inject_lyrics_text(songs)

        # Sort by title
        songs.sort(key=lambda s: s["title"].lower())

        return JSONResponse({
            "songs": songs,
            "total": len(songs),
            "download_dir": download_dir,
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
