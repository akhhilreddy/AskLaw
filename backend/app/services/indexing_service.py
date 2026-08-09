from bson import ObjectId
import uuid
from app.db.mongodb import (
    document_collection,
)

from app.services.vector_service import (
    store_chunk,
)


# =========================================================
# INDEX DOCUMENT
# =========================================================

def index_document(
    document_id: str,
    user_id: str,
):
    try:
        object_id = ObjectId(
            document_id
        )
    except Exception:
        return False

    document = document_collection.find_one(
        {
            "_id": object_id,
            "user_id": user_id,
        }
    )

    if not document:
        return False

    chunks = document.get(
        "chunks",
        []
    )

    if not chunks:
        return False

    for chunk in chunks:
        chunk_index = chunk["index"]
        page_number = chunk["page_number"]
        text = chunk["text"]

        chunk_id = str(
    uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"{document_id}_{chunk_index}",
    )
)

        store_chunk(
            chunk_id=chunk_id,
            text=text,
            document_id=document_id,
            user_id=user_id,
            filename=document["filename"],
            chunk_index=chunk_index,
            page_number=page_number,
        )

    return True