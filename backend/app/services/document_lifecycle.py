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
        {"$set": {"status": "failed", "failure_code": "processing_lease_expired", "failed_at": now, "vector_cleanup_pending": True},
         "$unset": {"processing_claim_id": "", "processing_lease_expires_at": ""}},
    )


def failure_code(exc):
    # No exception text, provider response, keys, filename or PII is persisted.
    if isinstance(exc, TimeoutError):
        return "indexing_timeout"
    if type(exc).__name__ == "NonRetryableEmbeddingError":
        return "embedding_rejected"
    return "indexing_failed"


def get_ready_document_ids(collection, user_id, document_id=None):
    from bson import ObjectId
    query = {"user_id": user_id, "status": {"$in": ["indexed", "ready"]}}
    if document_id:
        try:
            query["_id"] = ObjectId(document_id)
        except Exception:
            return []
    recover_stale_documents(collection, user_id)
    return [str(record["_id"]) for record in collection.find(query, {"_id": 1})]


def cleanup_failed_document(collection, record, user_id, cleanup):
    if record.get("status") != "failed" or not record.get("vector_cleanup_pending"):
        return
    try:
        cleanup(document_id=str(record["_id"]), user_id=user_id)
        collection.update_one({"_id": record["_id"], "user_id": user_id, "status": "failed"},
                              {"$set": {"vector_cleanup_pending": False}})
    except Exception:
        import logging
        logging.getLogger(__name__).warning("Failed-document vector cleanup unavailable; will retry on library access")
