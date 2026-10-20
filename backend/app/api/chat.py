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
from app.services.guest_service import consume_guest_question
from app.core.rate_limit import limit_chat
from app.services.conversation_service import get_conversation
import anyio
from starlette.concurrency import run_in_threadpool
import logging
from uuid import uuid4

logger = logging.getLogger(__name__)


class ClosingStreamingResponse(StreamingResponse):
    def __init__(self, body, request_id=None, **kwargs):
        self.iterator = body
        self.request_id = request_id or uuid4().hex
        super().__init__(body, **kwargs)

    async def __call__(self, scope, receive, send):
        status = "interrupted"
        try:
            await super().__call__(scope, receive, send)
            status = "closed"
        finally:
            # Closing the sync generator cancels its retrieval task promptly.
            # Run this off the ASGI loop, and shield cleanup from disconnect.
            with anyio.CancelScope(shield=True):
                close = getattr(self.iterator, "close", None)
                if close:
                    await run_in_threadpool(close)
            logger.info("chat_stream request_id=%s phase=transport status=%s", self.request_id, status)


router = APIRouter()


# =========================================================
# STREAM CHAT
# =========================================================

@router.post("/stream", dependencies=[Depends(limit_chat)])
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

    if request.conversation_id and get_conversation(request.conversation_id, user_id) is None:
        raise HTTPException(404, "Conversation not found")

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

        if document.get("status") in {"uploaded", "processing"}:
            raise HTTPException(
                status_code=409,
                detail="This document is still being indexed.",
            )

        if document.get("status") == "failed":
            raise HTTPException(
                status_code=409,
                detail="Document indexing failed.",
            )

    # -----------------------------------------------------
    # STREAM RESPONSE
    # -----------------------------------------------------

    consume_guest_question(current_user)
    request_id = uuid4().hex
    if request.conversation_id:
        body = stream_response(request.messages, user_id, request.document_id,
                               conversation_id=request.conversation_id, request_id=request_id)
    else:
        body = stream_response(request.messages, user_id, request.document_id, request_id=request_id)
    return ClosingStreamingResponse(
        body,
        request_id=request_id,
        headers={"X-Request-ID": request_id},
        media_type="application/x-ndjson",
    )
