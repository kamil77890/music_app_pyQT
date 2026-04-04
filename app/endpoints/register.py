from fastapi import APIRouter, Request

router = APIRouter(tags=["Register"])

TOKEN = {"token": ""}


@router.get("/Register")
async def register(request: Request):
    token = request.headers.get("token")
    TOKEN["token"] = token
    return {"TOKEN": TOKEN["token"]}
