from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
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

from app.services.document_service import (
    get_owned_document,
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

    if request.document_id:
        document = get_owned_document(
            document_id=request.document_id,
            user_id=user_id,
        )

        if document is None:
            raise HTTPException(
                status_code=404,
                detail="Document not found",
            )

    # -----------------------------------------------------
    # STREAM RESPONSE
    # -----------------------------------------------------

    return StreamingResponse(
        stream_response(
            request.messages,
            user_id,
            request.document_id,
        ),
        media_type="application/x-ndjson",
    )
