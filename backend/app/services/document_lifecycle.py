"""Document leases and public, sanitized failure codes."""
from datetime import datetime, timedelta, timezone

PROCESSING_LEASE = timedelta(minutes=30)


def recover_stale_documents(collection, user_id):
    now = datetime.now(timezone.utc)
    cutoff = now - PROCESSING_LEASE
    collection.update_many(
        {"user_id": user_id, "status": "processing", "$or": [
            {"processing_lease_expires_at": {"$lte": now}},
            {"processing_lease_expires_at": {"$exists": False}, "processing_started_at": {"$lte": cutoff}},
            {"processing_lease_expires_at": {"$exists": False}, "processing_started_at": {"$exists": False},
             "uploaded_at": {"$lte": cutoff}},
        ]},
        {"$set": {"status": "failed", "failure_code": "processing_lease_expired", "failed_at": now},
         "$unset": {"processing_claim_id": "", "processing_lease_expires_at": ""}},
    )


def failure_code(exc):
    # No exception text, provider response, keys, filename or PII is persisted.
    if isinstance(exc, TimeoutError):
        return "indexing_timeout"
    if type(exc).__name__ == "NonRetryableEmbeddingError":
        return "embedding_rejected"
    return "indexing_failed"
