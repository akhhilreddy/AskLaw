from pymongo import MongoClient

from app.core.config import settings

client = MongoClient(settings.MONGODB_URL)

db = client[settings.MONGODB_DATABASE]

user_collection = db["users"]
conversation_collection = db["conversations"]
document_collection = db["documents"]


def ensure_indexes():
    """Create indexes used by ownership-scoped list and history queries."""

    document_collection.create_index(
        [("user_id", 1), ("uploaded_at", -1)],
        name="documents_user_uploaded_at",
    )
    conversation_collection.create_index(
        [("user_id", 1), ("updated_at", -1)],
        name="conversations_user_updated_at",
    )
