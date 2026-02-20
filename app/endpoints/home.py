from fastapi import APIRouter, Request
from app.authorization import login_decorator

router = APIRouter(tags=["home"])


@login_decorator
@router.get("/")
async def home(request: Request):
    return {"message": "Lubie koty!"}
