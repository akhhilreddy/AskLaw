from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, model_validator


ChatContent = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=20_000),
]

DocumentId = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9a-fA-F]{24}$"),
]

class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: ChatContent


class ChatRequest(BaseModel):
    messages: Annotated[list[ChatMessage], Field(min_length=1, max_length=50)]
    document_id: DocumentId | None = None

    @model_validator(mode="after")
    def validate_total_message_size(self):
        if sum(len(message.content) for message in self.messages) > 100_000:
            raise ValueError("Combined message content is too large")
        return self


class ChatResponse(BaseModel):
    response: str
