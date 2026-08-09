from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)

from app.core.dependencies import (
    get_current_user,
)

from app.services.conversation_service import (
    create_conversation,
    get_user_conversations,
    get_conversation,
    add_message,
    delete_conversation,
    rename_conversation,
    generate_title_from_first_message,
)

router = APIRouter()


# =========================================================
# CREATE
# =========================================================

@router.post("/")
def create_new_conversation(
    current_user=Depends(
        get_current_user
    ),
):
    return create_conversation(
        user_id=str(
            current_user["_id"]
        )
    )


# =========================================================
# GET ALL USER CONVERSATIONS
# =========================================================

@router.get("/")
def get_conversations(
    current_user=Depends(
        get_current_user
    ),
):
    return get_user_conversations(
        user_id=str(
            current_user["_id"]
        )
    )


# =========================================================
# GET SINGLE CONVERSATION
# =========================================================

@router.get("/{conversation_id}")
def get_single_conversation(
    conversation_id: str,
    current_user=Depends(
        get_current_user
    ),
):
    conversation = get_conversation(
        conversation_id=conversation_id,
        user_id=str(
            current_user["_id"]
        ),
    )

    if not conversation:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found",
        )

    return conversation


# =========================================================
# ADD MESSAGE
# =========================================================

@router.post("/{conversation_id}/messages")
def create_message(
    conversation_id: str,
    message: dict,
    current_user=Depends(
        get_current_user
    ),
):
    role = message.get("role")
    content = message.get("content")

    if not role or not content:
        raise HTTPException(
            status_code=400,
            detail="Role and content are required",
        )

    saved_message = add_message(
        conversation_id=conversation_id,
        user_id=str(
            current_user["_id"]
        ),
        role=role,
        content=content,
    )

    if not saved_message:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found",
        )

    return saved_message


# =========================================================
# DELETE
# =========================================================

@router.delete("/{conversation_id}")
def delete_single_conversation(
    conversation_id: str,
    current_user=Depends(
        get_current_user
    ),
):
    deleted = delete_conversation(
        conversation_id=conversation_id,
        user_id=str(
            current_user["_id"]
        ),
    )

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found",
        )

    return {
        "message": "Conversation deleted successfully"
    }
# =========================================================
# AUTOMATIC TITLE
# =========================================================

@router.patch("/{conversation_id}/title")
def generate_conversation_title(
    conversation_id: str,
    current_user=Depends(
        get_current_user
    ),
):
    title = generate_title_from_first_message(
        conversation_id=conversation_id,
        user_id=str(
            current_user["_id"]
        ),
    )

    if title is None:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found or has no messages",
        )

    return {
        "message": "Conversation title generated successfully",
        "title": title,
    }

# =========================================================
# RENAME
# =========================================================

@router.patch("/{conversation_id}/rename")
def rename_single_conversation(
    conversation_id: str,
    title: str,
    current_user=Depends(
        get_current_user
    ),
):
    renamed_title = rename_conversation(
        conversation_id=conversation_id,
        user_id=str(
            current_user["_id"]
        ),
        title=title,
    )

    if renamed_title is None:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found",
        )

    return {
        "message": "Conversation renamed successfully",
        "title": renamed_title,
    }