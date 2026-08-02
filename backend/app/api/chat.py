from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.services.ai_service import stream_response
from app.schemas.chat import ChatRequest
from app.core.dependencies import get_current_user

router = APIRouter()


@router.post("/stream")
def chat_stream(
    request: ChatRequest,
    current_user=Depends(get_current_user),
):
    return StreamingResponse(
        stream_response(request.message),
        media_type="text/plain",
    )