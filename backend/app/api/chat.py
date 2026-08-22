from fastapi import (
    APIRouter,
    Depends,
)

from fastapi.responses import (
    StreamingResponse,
)

from app.services.ai_service import (
    stream_response,
)

from app.schemas.chat import (
    ChatRequest,
)

from app.core.dependencies import (
    get_current_user,
)


router = APIRouter()


# =========================================================
# STREAM CHAT
# =========================================================

@router.post("/stream")
def chat_stream(
    request: ChatRequest,
    current_user=Depends(
        get_current_user
    ),
):
    # -----------------------------------------------------
    # GET CURRENT USER ID
    # -----------------------------------------------------

    user_id = str(
        current_user["_id"]
    )

    # -----------------------------------------------------
    # STREAM RESPONSE
    # -----------------------------------------------------

    return StreamingResponse(
        stream_response(
            request.messages,
            user_id,
        ),
        media_type="application/x-ndjson",
    )