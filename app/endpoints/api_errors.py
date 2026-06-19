from typing import Any

from fastapi.responses import JSONResponse


def api_error(error_code: str, message: str, status_code: int, **extra: Any) -> JSONResponse:
    body = {
        "ok": False,
        "status": "failed",
        "error_code": error_code,
        "message": message,
    }
    body.update(extra)
    return JSONResponse(body, status_code=status_code)
