from pydantic import BaseModel

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    document_id: str | None = None


class ChatResponse(BaseModel):
    response: str
