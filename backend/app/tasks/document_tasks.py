import logging
import uuid

from bson import ObjectId
from pymongo import ReturnDocument

from app.core.celery_app import celery_app
from app.db.mongodb import document_collection

from app.services.vector_service import (
    create_collection,
    store_chunk,
)


logger = logging.getLogger(__name__)


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

    document = document_collection.find_one_and_update(
        {
            "_id": object_id,
            "user_id": user_id,
            "$or": [
                {"status": "uploaded"},
                {
                    "status": "processing",
                    "indexing_task_id": task_id,
                },
                {
                    "status": "processing",
                    "indexing_task_id": {"$exists": False},
                },
            ],
        },
        {
            "$set": {
                "status": "processing",
                "indexing_task_id": task_id,
            }
        },
        return_document=ReturnDocument.AFTER,
    )

    if not document:
        return {
            "success": False,
            "message": "Document not available for indexing",
        }

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

        indexed_count = 0

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

            store_chunk(
                chunk_id=point_id,
                text=chunk_text,
                document_id=document_id,
                user_id=user_id,
                filename=filename,
                chunk_index=chunk_index,
                page_number=page_number,
            )

            indexed_count += 1

    except Exception as exc:
        logger.exception(
            "Document indexing attempt failed for document_id=%s (attempt %s of %s)",
            document_id,
            self.request.retries + 1,
            self.max_retries + 1,
        )

        if self.request.retries < self.max_retries:
            raise self.retry(
                exc=exc,
                countdown=5 * (self.request.retries + 1),
            )

        document_collection.update_one(
            {
                "_id": object_id,
                "user_id": user_id,
                "indexing_task_id": task_id,
            },
            {
                "$set": {"status": "failed"},
                "$unset": {"indexing_task_id": ""},
            },
        )
        raise

    document_collection.update_one(
        {
            "_id": object_id,
            "user_id": user_id,
            "indexing_task_id": task_id,
        },
        {
            "$set": {
                "status": "indexed",
            },
            "$unset": {
                "indexing_task_id": "",
            },
        },
    )

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
