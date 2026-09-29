from pymongo import MongoClient

from app.core.config import settings

client = MongoClient(settings.MONGODB_URL)

db = client[settings.MONGODB_DATABASE]

user_collection = db["users"]
conversation_collection = db["conversations"]
document_collection = db["documents"]
auth_code_collection = db["auth_codes"]


def ensure_indexes():
    """Create indexes used by ownership-scoped list and history queries."""

    user_collection.create_index(
        [("email", 1)],
        name="users_email_unique",
        unique=True,
    )

    document_collection.create_index(
        [("user_id", 1), ("uploaded_at", -1)],
        name="documents_user_uploaded_at",
    )
    conversation_collection.create_index(
        [("user_id", 1), ("updated_at", -1)],
        name="conversations_user_updated_at",
    )
    auth_code_collection.create_index(
        [("email", 1), ("purpose", 1)],
        name="auth_codes_email_purpose_unique",
        unique=True,
    )
    auth_code_collection.create_index(
        [("expires_at", 1)],
        name="auth_codes_expiry_ttl",
        expireAfterSeconds=0,
    )
