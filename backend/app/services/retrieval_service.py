from app.services.vector_service import (
    search_similar_chunks,
)


# =========================================================
# RETRIEVE RELEVANT DOCUMENT CHUNKS
# =========================================================

def retrieve_relevant_chunks(
    query: str,
    user_id: str,
    limit: int = 5,
):
    """
    Find the most relevant document chunks
    for the user's question.
    """

    # -----------------------------------------------------
    # Search Qdrant
    # -----------------------------------------------------

    results = search_similar_chunks(
        query=query,
        user_id=user_id,
        limit=limit,
    )

    # -----------------------------------------------------
    # Convert Qdrant results into simple dictionaries
    # -----------------------------------------------------

    chunks = []

    for result in results:
        payload = result.payload or {}

        chunks.append(
            {
                "score": result.score,
                "document_id": payload.get(
                    "document_id"
                ),
                "filename": payload.get(
                    "filename"
                ),
                "chunk_index": payload.get(
                    "chunk_index"
                ),
                "page_number": payload.get(
                    "page_number"
                ),
                "text": payload.get(
                    "text"
                ),
            }
        )

    return chunks