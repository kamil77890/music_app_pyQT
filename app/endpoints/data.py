from fastapi import APIRouter, Request
from app.logic.handle_data import handle_data

router = APIRouter(tags=["data"])


@router.post("/api/data")
async def handle_data_endpoint(request: Request):
    new_data = await request.json()
    handle_data(new_data)
    return {"message": "Data received"}
