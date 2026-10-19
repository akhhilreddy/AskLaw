"""Small, server-enforced demo policy; normal accounts are unaffected."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException

from app.db.mongodb import user_collection

GUEST_LIFETIME = timedelta(hours=1)
GUEST_CHAT_LIMIT = 5


def ensure_guest_active(user):
    if not user.get("is_guest"):
        return
    expires = user.get("guest_expires_at")
    # PyMongo returns naive UTC datetimes by default.
    if expires is None or expires.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc):
        raise HTTPException(401, "Your guest session has expired. Create an account to continue.")


def require_registered_user(user):
    if user.get("is_guest"):
        raise HTTPException(403, "Create an account to use this feature. Guest access includes web research only.")


def create_guest_user():
    now = datetime.now(timezone.utc)
    user = {
        "name": "Guest", "email": f"{uuid4().hex}@guest.asklaw.invalid",
        "is_guest": True, "email_verified": True, "auth_version": 0,
        "guest_chat_count": 0, "created_at": now,
        "guest_expires_at": now + GUEST_LIFETIME,
    }
    user["_id"] = user_collection.insert_one(user).inserted_id
    return user


def consume_guest_question(user):
    if not user.get("is_guest"):
        return
    ensure_guest_active(user)
    # Atomic quota check prevents concurrent requests from exceeding the limit.
    result = user_collection.update_one(
        {"_id": user["_id"], "is_guest": True,
         "guest_expires_at": {"$gt": datetime.now(timezone.utc)},
         "guest_chat_count": {"$lt": GUEST_CHAT_LIMIT}},
        {"$inc": {"guest_chat_count": 1}},
    )
    if not result.modified_count:
        raise HTTPException(429, "You have used your 5 guest questions. Create an account to continue.")
