from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.dependencies import get_current_user



from app.services.conversation_service import (
    create_conversation,
    get_user_conversations,
    add_message,
    get_conversation,
    update_conversation_title,
    generate_conversation_title,
)


router = APIRouter()


class AddMessageRequest(BaseModel):
    role: str
    content: str


@router.get("/")
def get_conversations(
    current_user=Depends(get_current_user),
):
    conversations = get_user_conversations(
        str(current_user["_id"])
    )

    return conversations


@router.post("/")
def create_new_conversation(
    current_user=Depends(get_current_user),
):
    conversation = create_conversation(
        str(current_user["_id"])
    )

    return {
        "id": str(conversation["_id"]),
        "title": conversation["title"],
        "messages": conversation["messages"],
        "created_at": conversation["created_at"],
        "updated_at": conversation["updated_at"],
    }


@router.post("/{conversation_id}/messages")
def add_conversation_message(
    conversation_id: str,
    request: AddMessageRequest,
    current_user=Depends(get_current_user),
):
    success = add_message(
        conversation_id=conversation_id,
        user_id=str(current_user["_id"]),
        role=request.role,
        content=request.content,
    )

    if not success:
        return {
            "success": False,
            "message": "Conversation not found",
        }

    return {
        "success": True,
    }

@router.get("/{conversation_id}")
def get_single_conversation(
    conversation_id: str,
    current_user=Depends(get_current_user),
):
    conversation = get_conversation(
        conversation_id=conversation_id,
        user_id=str(current_user["_id"]),
    )

    if not conversation:
        return {
            "success": False,
            "message": "Conversation not found",
        }

    return {
        "id": str(conversation["_id"]),
        "title": conversation["title"],
        "messages": conversation["messages"],
        "created_at": conversation["created_at"],
        "updated_at": conversation["updated_at"],
    }


@router.patch("/{conversation_id}/title")
def update_title(
    conversation_id: str,
    current_user=Depends(get_current_user),
):
    conversation = get_conversation(
        conversation_id=conversation_id,
        user_id=str(current_user["_id"]),
    )

    if not conversation:
        return {
            "success": False,
            "message": "Conversation not found",
        }

    if conversation.get("title") != "New Chat":
        return {
            "success": True,
            "title": conversation.get("title"),
        }

    messages = conversation.get("messages", [])

    if not messages:
        return {
            "success": True,
            "title": "New Chat",
        }

    first_user_message = next(
        (
            message["content"]
            for message in messages
            if message.get("role") == "user"
        ),
        "",
    )

    title = generate_conversation_title(
        first_user_message
    )

    update_conversation_title(
        conversation_id=conversation_id,
        user_id=str(current_user["_id"]),
        title=title,
    )

    return {
        "success": True,
        "title": title,
    }