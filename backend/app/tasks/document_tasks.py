import uuid

from bson import ObjectId

from app.core.celery_app import celery_app
from app.db.mongodb import document_collection

from app.services.vector_service import (
    create_collection,
    store_chunk,
)


# =========================================================
# INDEX DOCUMENT IN BACKGROUND
# =========================================================

@celery_app.task(
    name="app.tasks.document_tasks.index_document"
)
def index_document(
    document_id: str,
    user_id: str,
):
    """
    Load a document from MongoDB and
    store all of its chunks in Qdrant.
    """

    # -----------------------------------------------------
    # MAKE SURE QDRANT COLLECTION EXISTS
    # -----------------------------------------------------

    create_collection()

    # -----------------------------------------------------
    # GET DOCUMENT FROM MONGODB
    # -----------------------------------------------------

    document = document_collection.find_one(
        {
            "_id": ObjectId(document_id),
            "user_id": user_id,
        }
    )

    if not document:
        return {
            "success": False,
            "message": "Document not found",
        }

    # -----------------------------------------------------
    # GET DOCUMENT DATA
    # -----------------------------------------------------

    filename = document.get(
        "filename"
    )

    chunks = document.get(
        "chunks",
        [],
    )

    # -----------------------------------------------------
    # INDEX EVERY CHUNK
    # -----------------------------------------------------

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

        # -------------------------------------------------
        # CREATE VALID QDRANT POINT ID
        # -------------------------------------------------

        point_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_DNS,
                f"{document_id}_{chunk_index}",
            )
        )

        # -------------------------------------------------
        # STORE IN QDRANT
        # -------------------------------------------------

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

    # -----------------------------------------------------
    # RETURN TASK RESULT
    # -----------------------------------------------------

    return {
        "success": True,
        "document_id": document_id,
        "chunks_indexed": indexed_count,
    }