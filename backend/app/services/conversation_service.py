from datetime import datetime, timezone

from app.db.mongodb import conversation_collection


def create_conversation(user_id: str, title: str = "New Chat"):
    now = datetime.now(timezone.utc)

    conversation = {
        "user_id": user_id,
        "title": title,
        "messages": [],
        "created_at": now,
        "updated_at": now,
    }

    result = conversation_collection.insert_one(conversation)

    conversation["_id"] = result.inserted_id

    return conversation

def get_user_conversations(user_id: str):
    conversations = conversation_collection.find(
        {"user_id": user_id}
    ).sort("updated_at", -1)

    return [
        {
            "id": str(conversation["_id"]),
            "title": conversation.get("title", "New Chat"),
            "messages": conversation.get("messages", []),
            "created_at": conversation.get("created_at"),
            "updated_at": conversation.get("updated_at"),
        }
        for conversation in conversations
    ]
def add_message(
    conversation_id: str,
    user_id: str,
    role: str,
    content: str,
):
    from bson import ObjectId
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)

    result = conversation_collection.update_one(
        {
            "_id": ObjectId(conversation_id),
            "user_id": user_id,
        },
        {
            "$push": {
                "messages": {
                    "role": role,
                    "content": content,
                }
            },
            "$set": {
                "updated_at": now,
            },
        },
    )

    return result.modified_count > 0

def update_conversation_title(
    conversation_id: str,
    user_id: str,
    title: str,
):
    from bson import ObjectId
    from datetime import datetime, timezone

    result = conversation_collection.update_one(
        {
            "_id": ObjectId(conversation_id),
            "user_id": user_id,
        },
        {
            "$set": {
                "title": title,
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )

    return result.modified_count > 0

from bson import ObjectId


def get_conversation(
    conversation_id: str,
    user_id: str,
):
    conversation = conversation_collection.find_one(
        {
            "_id": ObjectId(conversation_id),
            "user_id": user_id,
        }
    )

    return conversation

def generate_conversation_title(message: str):
    title = " ".join(message.strip().split())

    if not title:
        return "New Chat"

    if len(title) <= 45:
        return title

    return title[:45].rsplit(" ", 1)[0] + "..."