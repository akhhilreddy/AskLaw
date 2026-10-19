from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints, field_validator
import logging


ConversationContent = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=20_000),
]


class ConversationMessageCreate(BaseModel):
    role: Literal["user", "assistant"]
    content: ConversationContent
    availability_receipt: str | None = None

    @field_validator("availability_receipt", mode="before")
    @classmethod
    def cap_receipt(cls, value):
        from app.services.availability import RECEIPT_MAX_BYTES
        if value is not None and (not isinstance(value, str) or len(value) > RECEIPT_MAX_BYTES):
            logging.getLogger(__name__).warning("Invalid availability receipt field ignored")
            return None
        return value
