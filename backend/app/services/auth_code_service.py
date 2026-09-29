import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.db.mongodb import auth_code_collection
from app.services.email_service import send_auth_code


VERIFY_EMAIL = "verify_email"
RESET_PASSWORD = "reset_password"


def _hash_code(email: str, purpose: str, code: str) -> str:
    message = f"{email}:{purpose}:{code}".encode("utf-8")
    return hmac.new(
        settings.email_otp_secret.encode("utf-8"),
        message,
        hashlib.sha256,
    ).hexdigest()


def issue_code(email: str, purpose: str) -> bool:
    """Create and send an OTP. Returns False during the resend cooldown."""

    now = datetime.now(timezone.utc)
    current = auth_code_collection.find_one(
        {"email": email, "purpose": purpose},
        {"created_at": 1},
    )
    if current and current.get("created_at"):
        created_at = current["created_at"]
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        elapsed = (now - created_at).total_seconds()
        if elapsed < settings.EMAIL_OTP_RESEND_COOLDOWN_SECONDS:
            return False

    code = f"{secrets.randbelow(1_000_000):06d}"
    auth_code_collection.replace_one(
        {"email": email, "purpose": purpose},
        {
            "email": email,
            "purpose": purpose,
            "code_hash": _hash_code(email, purpose, code),
            "attempts": 0,
            "created_at": now,
            "expires_at": now
            + timedelta(minutes=settings.EMAIL_OTP_EXPIRE_MINUTES),
        },
        upsert=True,
    )

    try:
        send_auth_code(email, code, purpose)
    except Exception:
        auth_code_collection.delete_one({"email": email, "purpose": purpose})
        raise

    return True


def consume_code(email: str, purpose: str, code: str) -> bool:
    now = datetime.now(timezone.utc)
    code_hash = _hash_code(email, purpose, code)
    record = auth_code_collection.find_one_and_delete(
        {
            "email": email,
            "purpose": purpose,
            "code_hash": code_hash,
            "expires_at": {"$gt": now},
            "attempts": {"$lt": settings.EMAIL_OTP_MAX_ATTEMPTS},
        }
    )
    if record:
        return True

    auth_code_collection.update_one(
        {
            "email": email,
            "purpose": purpose,
            "expires_at": {"$gt": now},
            "attempts": {"$lt": settings.EMAIL_OTP_MAX_ATTEMPTS},
        },
        {"$inc": {"attempts": 1}},
    )
    return False
