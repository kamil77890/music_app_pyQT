from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
import os
from ..config.stałe import Parameters

router = APIRouter(tags=["download"])


@router.get("/songs/{filename:path}")
async def download_file(filename: str):
    file_path = os.path.join(Parameters.get_download_dir(), filename)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=file_path, filename=filename, media_type="application/octet-stream")
