from fastapi import APIRouter, Query, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from app.logic.ultimate_downloader import download_song, download_playlist
from app.authorization import login_decorator
import os

router = APIRouter(tags=["download"])


def wrap_file_response(file_path: str):
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        path=file_path,
        filename=os.path.basename(file_path),
        media_type="application/octet-stream",
    )


@login_decorator
@router.get("/download")
async def download(
    request: Request,
    videoId: str = Query(default="0"),
    id: str = Query(default="0"),
    playlistId: str = Query(default="0"),
    format: str = Query(default="mp3")
):

    if playlistId != "0":
        file_path = await run_in_threadpool(download_playlist, playlistId, id, format)
    else:
        file_path = await run_in_threadpool(download_song, videoId, id, format)

    return wrap_file_response(file_path)
