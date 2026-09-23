from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints


ConversationContent = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=20_000),
]


class ConversationMessageCreate(BaseModel):
    role: Literal["user", "assistant"]
    content: ConversationContent
