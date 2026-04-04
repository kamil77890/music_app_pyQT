from fastapi import APIRouter
from fastapi.responses import JSONResponse
from app.logic.metadata.add_metadata import verify_metadata
from app.config.stałe import Parameters
import os

router = APIRouter(prefix="/api", tags=["songs"])


@router.get("/songs")
async def get_songs():
    try:
        download_dir = Parameters.get_download_dir()
        if not os.path.isdir(download_dir):
            return JSONResponse({"songs": [], "message": "Download directory not found"})

        songs = []
        supported_extensions = (".mp3", ".mp4", ".m4a", ".flac", ".ogg", ".wav")

        for filename in os.listdir(download_dir):
            if filename.lower().endswith(supported_extensions):
                file_path = os.path.join(download_dir, filename)
                ext = os.path.splitext(filename)[1].lstrip(".").lower()
                meta = verify_metadata(file_path, ext)

                song_entry = {
                    "filename": filename,
                    "title": meta.get("title", os.path.splitext(filename)[0]),
                    "artist": meta.get("artist", "Unknown Artist"),
                    "videoId": meta.get("videoId", ""),
                    "cover": meta.get("cover", ""),
                    "format": ext,
                    "size_bytes": os.path.getsize(file_path),
                }
                songs.append(song_entry)

        # Sort by title
        songs.sort(key=lambda s: s["title"].lower())

        return JSONResponse({
            "songs": songs,
            "total": len(songs),
            "download_dir": download_dir,
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
