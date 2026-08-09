from datetime import datetime, timezone

from bson import ObjectId

from app.db.mongodb import conversation_collection


# =========================================================
# CREATE CONVERSATION
# =========================================================

def create_conversation(user_id: str):
    now = datetime.now(timezone.utc)

    conversation = {
        "user_id": user_id,
        "title": "New Chat",
        "messages": [],
        "created_at": now,
        "updated_at": now,
    }

    result = conversation_collection.insert_one(
        conversation
    )

    conversation["id"] = str(result.inserted_id)
    del conversation["_id"]

    return conversation


# =========================================================
# GET USER CONVERSATIONS
# =========================================================

def get_user_conversations(user_id: str):
    conversations = conversation_collection.find(
        {
            "user_id": user_id
        }
    ).sort(
        "updated_at",
        -1
    )

    result = []

    for conversation in conversations:
        result.append(
            {
                "id": str(conversation["_id"]),
                "title": conversation.get(
                    "title",
                    "New Chat"
                ),
                "created_at": conversation.get(
                    "created_at"
                ),
                "updated_at": conversation.get(
                    "updated_at"
                ),
            }
        )

    return result


# =========================================================
# GET SINGLE CONVERSATION
# =========================================================

def get_conversation(
    conversation_id: str,
    user_id: str,
):
    try:
        object_id = ObjectId(
            conversation_id
        )
    except Exception:
        return None

    conversation = conversation_collection.find_one(
        {
            "_id": object_id,
            "user_id": user_id,
        }
    )

    if not conversation:
        return None

    messages = []

    for message in conversation.get(
        "messages",
        []
    ):
        messages.append(
            {
                "id": str(
                    message.get(
                        "_id",
                        ObjectId()
                    )
                ),
                "role": message["role"],
                "content": message["content"],
            }
        )

    return {
        "id": str(conversation["_id"]),
        "title": conversation.get(
            "title",
            "New Chat"
        ),
        "messages": messages,
        "created_at": conversation.get(
            "created_at"
        ),
        "updated_at": conversation.get(
            "updated_at"
        ),
    }


# =========================================================
# ADD MESSAGE
# =========================================================

def add_message(
    conversation_id: str,
    user_id: str,
    role: str,
    content: str,
):
    try:
        object_id = ObjectId(
            conversation_id
        )
    except Exception:
        return None

    message = {
        "_id": ObjectId(),
        "role": role,
        "content": content,
    }

    result = conversation_collection.update_one(
        {
            "_id": object_id,
            "user_id": user_id,
        },
        {
            "$push": {
                "messages": message
            },
            "$set": {
                "updated_at": datetime.now(
                    timezone.utc
                )
            },
        },
    )

    if result.matched_count == 0:
        return None

    return {
        "id": str(message["_id"]),
        "role": role,
        "content": content,
    }


# =========================================================
# DELETE CONVERSATION
# =========================================================

def delete_conversation(
    conversation_id: str,
    user_id: str,
):
    try:
        object_id = ObjectId(
            conversation_id
        )
    except Exception:
        return False

    result = conversation_collection.delete_one(
        {
            "_id": object_id,
            "user_id": user_id,
        }
    )

    return result.deleted_count > 0


# =========================================================
# RENAME CONVERSATION
# =========================================================

def rename_conversation(
    conversation_id: str,
    user_id: str,
    title: str,
):
    # Clean whitespace
    title = " ".join(
        title.strip().split()
    )

    if not title:
        return None

    # Maximum title length
    title = title[:80]

    try:
        object_id = ObjectId(
            conversation_id
        )
    except Exception:
        return None

    result = conversation_collection.update_one(
        {
            "_id": object_id,
            "user_id": user_id,
        },
        {
            "$set": {
                "title": title,
                "updated_at": datetime.now(
                    timezone.utc
                ),
            }
        },
    )

    # IMPORTANT:
    # matched_count tells us whether the
    # conversation actually exists.
    #
    # modified_count can be 0 when the user
    # saves the exact same title.

    if result.matched_count == 0:
        return None

    return title

# =========================================================
# GENERATE AUTOMATIC TITLE
# =========================================================

def generate_title_from_first_message(
    conversation_id: str,
    user_id: str,
):
    try:
        object_id = ObjectId(
            conversation_id
        )
    except Exception:
        return None

    conversation = conversation_collection.find_one(
        {
            "_id": object_id,
            "user_id": user_id,
        }
    )

    if not conversation:
        return None

    messages = conversation.get(
        "messages",
        []
    )

    if not messages:
        return None

    # Find the first user message
    first_user_message = None

    for message in messages:
        if message.get("role") == "user":
            first_user_message = message.get(
                "content",
                ""
            )
            break

    if not first_user_message:
        return None

    # Clean the message
    title = " ".join(
        first_user_message.strip().split()
    )

    # Make it suitable for a sidebar title
    if len(title) > 60:
        title = title[:60].rsplit(
            " ",
            1
        )[0] + "..."

    result = conversation_collection.update_one(
        {
            "_id": object_id,
            "user_id": user_id,
        },
        {
            "$set": {
                "title": title,
                "updated_at": datetime.now(
                    timezone.utc
                ),
            }
        },
    )

    if result.matched_count == 0:
        return None

    return title