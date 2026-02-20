from fastapi import APIRouter, Request
from app.authorization import login_decorator

router = APIRouter(tags=["Register"])

TOKEN = {"token": ""}


@router.get("/Register")
@login_decorator
async def register(request: Request):
    token = request.headers.get("token")
    TOKEN["token"] = token
    return {"TOKEN": TOKEN["token"]}
