import logging
import uuid
from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument

from app.core.celery_app import celery_app
from app.db.mongodb import document_collection
from app.services.document_lifecycle import PROCESSING_LEASE, failure_code

from app.services.vector_service import (
    NonRetryableEmbeddingError,
    create_collection,
    store_chunks,
    delete_document_chunks,
)


logger = logging.getLogger(__name__)


class ProcessingLeaseLost(RuntimeError):
    pass


# =========================================================
# INDEX DOCUMENT IN BACKGROUND
# =========================================================

@celery_app.task(
    bind=True,
    name="app.tasks.document_tasks.index_document",
    max_retries=2,
    default_retry_delay=5,
)
def index_document(
    self,
    document_id: str,
    user_id: str,
):
    """
    Load a document from MongoDB and
    store all of its chunks in Qdrant.
    """

    try:
        object_id = ObjectId(
            document_id
        )
    except Exception:
        return {
            "success": False,
            "message": "Invalid document ID",
        }

    # -----------------------------------------------------
    # ATOMICALLY CLAIM THE DOCUMENT
    #
    # A different duplicate/redelivered task must not index a document that
    # has already finished or is being handled by another task. Celery retries
    # preserve their task ID and may resume the same claim.
    # -----------------------------------------------------

    task_id = self.request.id or f"direct:{document_id}"
    claim_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc)

    document = document_collection.find_one_and_update(
        {
            "_id": object_id,
            "user_id": user_id,
            "$or": [
                {"status": "uploaded"},
                {
                    "status": "processing",
                    "indexing_task_id": task_id,
                    "processing_claim_id": {"$exists": False},
                },
                {
                    "status": "processing",
                    "indexing_task_id": {"$exists": False},
                    "processing_claim_id": {"$exists": False},
                },
                {"status": "processing", "processing_lease_expires_at": {"$lte": now}},
                {"status": "failed", "failure_code": "processing_lease_expired", "vector_cleanup_pending": False},
            ],
        },
        {
            "$set": {
                "status": "processing",
                "indexing_task_id": task_id,
                "processing_claim_id": claim_id,
                "processing_started_at": now,
                "processing_lease_expires_at": now + PROCESSING_LEASE,
            }
        },
        return_document=ReturnDocument.AFTER,
    )

    if not document:
        return {
            "success": False,
            "message": "Document not available for indexing",
        }

    claim_filter = {"_id": object_id, "user_id": user_id, "indexing_task_id": task_id,
                    "processing_claim_id": claim_id, "status": "processing"}

    def heartbeat():
        current = datetime.now(timezone.utc)
        result = document_collection.update_one(
            {**claim_filter, "processing_lease_expires_at": {"$gt": current}},
            {"$set": {"processing_lease_expires_at": current + PROCESSING_LEASE}},
        )
        if not result.matched_count:
            raise ProcessingLeaseLost("Document processing lease is no longer owned")

    def terminal_failure(exc):
        result = document_collection.update_one(claim_filter, {
            "$set": {"status": "failed", "failure_code": failure_code(exc),
                     "failed_at": datetime.now(timezone.utc), "vector_cleanup_pending": True},
            "$unset": {"indexing_task_id": "", "processing_claim_id": "", "processing_lease_expires_at": ""},
        })
        if not result.matched_count:
            return
        from app.services.document_lifecycle import cleanup_failed_document
        cleanup_failed_document(document_collection, {"_id": object_id, "status": "failed", "vector_cleanup_pending": True},
                                user_id, delete_document_chunks)

    # -----------------------------------------------------
    # GET DOCUMENT DATA
    # -----------------------------------------------------

    try:
        # -------------------------------------------------
        # MAKE SURE QDRANT COLLECTION EXISTS
        # -------------------------------------------------

        create_collection()

        filename = document.get(
            "filename"
        )

        chunks = document.get(
            "chunks",
            [],
        )

        # -------------------------------------------------
        # INDEX EVERY CHUNK
        # -------------------------------------------------

        indexable_chunks = []

        for chunk in chunks:

            chunk_index = chunk.get(
                "index"
            )

            chunk_text = chunk.get(
                "text"
            )

            page_number = chunk.get(
                "page_number"
            )

            if not chunk_text:
                continue

            point_id = str(
                uuid.uuid5(
                    uuid.NAMESPACE_DNS,
                    f"{document_id}_{chunk_index}",
                )
            )

            indexable_chunks.append(
                {
                    "chunk_id": point_id,
                    "text": chunk_text,
                    "document_id": document_id,
                    "user_id": user_id,
                    "filename": filename,
                    "chunk_index": chunk_index,
                    "page_number": page_number,
                }
            )

        indexed_count = store_chunks(indexable_chunks, progress_callback=heartbeat)

    except ProcessingLeaseLost:
        # A stale/redelivered worker must not alter a newer claim's state.
        logger.warning("Document indexing stopped after losing its processing lease")
        return {"success": False, "message": "Processing lease lost"}

    except NonRetryableEmbeddingError as exc:
        logger.error(
            "Document indexing failed with a non-retryable embedding error "
            "for document_id=%s",
            document_id,
        )
        terminal_failure(exc)
        raise

    except Exception as exc:
        logger.error(
            "Document indexing attempt failed for document_id=%s (attempt %s of %s)",
            document_id,
            self.request.retries + 1,
            self.max_retries + 1,
        )

        if self.request.retries < self.max_retries:
            document_collection.update_one(claim_filter, {"$unset": {"processing_claim_id": ""}})
            raise self.retry(
                exc=exc,
                countdown=5 * (self.request.retries + 1),
            )

        terminal_failure(exc)
        raise

    completion = document_collection.update_one(
        {**claim_filter, "processing_lease_expires_at": {"$gt": datetime.now(timezone.utc)}},
        {
            "$set": {
                "status": "indexed",
            },
            "$unset": {
                "indexing_task_id": "",
                "processing_claim_id": "",
                "processing_lease_expires_at": "",
                "failure_code": "",
                "failed_at": "",
            },
        },
    )

    if not completion.matched_count:
        return {"success": False, "message": "Processing lease lost"}

    logger.info(
        "Document indexing completed for document_id=%s with %s chunks",
        document_id,
        indexed_count,
    )

    # -----------------------------------------------------
    # RETURN TASK RESULT
    # -----------------------------------------------------

    return {
        "success": True,
        "document_id": document_id,
        "chunks_indexed": indexed_count,
    }
