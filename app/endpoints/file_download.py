from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse
from ..config.stałe import Parameters
from app.endpoints.api_errors import api_error

router = APIRouter(tags=["download"])


@router.get("/songs/{filename:path}")
async def download_file(filename: str):
    base_dir = Path(Parameters.get_download_dir()).resolve()
    file_path = (base_dir / filename).resolve()
    if file_path != base_dir and base_dir not in file_path.parents:
        return api_error("PATH_TRAVERSAL_BLOCKED", "Path is outside the download directory.", 403)
    if not file_path.is_file():
        return api_error("FILE_NOT_FOUND", "File not found.", 404)
    return FileResponse(path=str(file_path), filename=file_path.name, media_type="application/octet-stream")
