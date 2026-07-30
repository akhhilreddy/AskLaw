from fastapi import APIRouter, Depends

from app.schemas.chat import ChatRequest, ChatResponse
from app.core.dependencies import get_current_user

router = APIRouter()


@router.post("/", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    current_user=Depends(get_current_user)
):
    return ChatResponse(
        response=f"Hello {current_user['name']}, you asked: {request.message}"
    )