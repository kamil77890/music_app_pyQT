from fastapi import HTTPException, Request
from typing import Callable


def login_decorator(endpoint: Callable):
    async def wrapper(request: Request, *args, **kwargs):
        token = request.headers.get("token")
        if token == "cos":
            return await endpoint(request, *args, **kwargs)
        else:
            raise HTTPException(status_code=403, detail="Brak dostępu")
    return wrapper
