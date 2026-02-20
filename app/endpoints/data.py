from fastapi import APIRouter, Request
from app.authorization import login_decorator
from app.logic.handle_data import handle_data

router = APIRouter(tags=["data"])


@login_decorator
@router.post("/api/data")
async def handle_data_endpoint(request: Request):
    new_data = await request.json()
    handle_data(new_data)
    return {"message": "Data received"}
