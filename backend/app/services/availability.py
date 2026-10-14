"""Allowlisted operational notices and short-lived non-JWT attestations."""
import base64
import hashlib
import hmac
import json
import logging
import time

from app.core.config import settings

NOTICE_TYPES = frozenset({"web_unavailable", "web_partial", "rag_unavailable", "rag_timeout", "rag_busy", "research_timeout"})
NOTICE_MESSAGES = {
    "web_unavailable": "Web search is temporarily unavailable, try again shortly.",
    "web_partial": "Some web searches were unavailable; web coverage may be incomplete.",
    "rag_unavailable": "Document research is temporarily unavailable; only available web evidence was used.",
    "rag_timeout": "Document research timed out; only available evidence was used.",
    "rag_busy": "Document research is busy; try again shortly.",
    "research_timeout": "Research timed out; try again shortly.",
}
RECEIPT_MAX_BYTES = 4096
RECEIPT_LIFETIME_SECONDS = 300
logger = logging.getLogger(__name__)


def notices(types):
    return [{"type": kind} for kind in dict.fromkeys(types) if kind in NOTICE_TYPES]


def _key():
    return hmac.new(settings.SECRET_KEY.encode(), b"AskLaw availability receipt v1", hashlib.sha256).digest()


def _encode(value):
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _decode(value):
    return base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)


def sign_availability(user_id, conversation_id, answer, items, *, availability_only=False, now=None):
    if not conversation_id or not items:
        return None
    kinds = [item.get("type") for item in items]
    if notices(kinds) != items:
        raise ValueError("Invalid availability notices")
    payload = json.dumps({"v": 1, "user_id": str(user_id), "conversation_id": str(conversation_id),
                          "answer_hash": hashlib.sha256(answer.strip().encode()).hexdigest(),
                          "notices": items, "availability_only": bool(availability_only),
                          "issued_at": int(time.time() if now is None else now)},
                         separators=(",", ":"), sort_keys=True).encode()
    receipt = _encode(payload) + "." + _encode(hmac.new(_key(), payload, hashlib.sha256).digest())
    if len(receipt) > RECEIPT_MAX_BYTES:
        raise ValueError("Availability receipt exceeds size limit")
    return receipt


def verify_availability(receipt, user_id, conversation_id, answer, *, now=None):
    if receipt is None:
        return {}
    try:
        if not isinstance(receipt, str) or len(receipt) > RECEIPT_MAX_BYTES:
            raise ValueError()
        encoded, signature = receipt.split(".")
        raw = _decode(encoded)
        if not hmac.compare_digest(hmac.new(_key(), raw, hashlib.sha256).digest(), _decode(signature)):
            raise ValueError()
        payload = json.loads(raw)
        if set(payload) != {"v", "user_id", "conversation_id", "answer_hash", "notices", "availability_only", "issued_at"}:
            raise ValueError()
        age = (time.time() if now is None else now) - payload["issued_at"]
        if payload["v"] != 1 or type(payload["issued_at"]) is not int or not 0 <= age <= RECEIPT_LIFETIME_SECONDS:
            raise ValueError()
        if payload["user_id"] != str(user_id) or payload["conversation_id"] != str(conversation_id):
            raise ValueError()
        if not hmac.compare_digest(payload["answer_hash"], hashlib.sha256(answer.strip().encode()).hexdigest()):
            raise ValueError()
        items = payload["notices"]
        if not isinstance(items, list) or not items or len(items) > len(NOTICE_TYPES) or type(payload["availability_only"]) is not bool:
            raise ValueError()
        if notices([item["type"] for item in items]) != items:
            raise ValueError()
        return {"availability_notices": items, "availability_only": payload["availability_only"]}
    except Exception:
        logger.warning("Availability receipt verification failed; saving message without notices")
        return {}


class SearchResponse(dict):
    """Failure provenance added by our HTTP client, never decoded from an engine."""
    def __init__(self, *args, unavailable=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.unavailable = unavailable


class WebResults(list):
    def __init__(self, values=(), notice_types=()):
        super().__init__(values)
        self.availability_notices = notices(notice_types)
