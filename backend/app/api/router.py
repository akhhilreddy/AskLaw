from fastapi import APIRouter

from app.api.health import router as health_router
from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.conversation import router as conversation_router
from app.api.document import router as document_router
from app.api.agreement import router as agreement_router
from app.api.complaint import router as complaint_router

api_router = APIRouter()
api_router.include_router(complaint_router, prefix="/complaints", tags=["Consumer complaint preparation"])
api_router.include_router(agreement_router, prefix="/agreements", tags=["Agreement review"])

api_router.include_router(health_router)

api_router.include_router(
    auth_router,
    prefix="/auth",
    tags=["Authentication"],
)

api_router.include_router(
    chat_router,
    prefix="/chat",
    tags=["Chat"],
)

api_router.include_router(
    conversation_router,
    prefix="/conversations",
    tags=["Conversations"],
)

api_router.include_router(
    document_router,
    prefix="/documents",
    tags=["Documents"],
)
