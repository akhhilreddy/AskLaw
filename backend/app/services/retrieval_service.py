from app.services.vector_service import (
    search_similar_chunks,
)


# =========================================================
# RETRIEVAL SETTINGS
# =========================================================

# Avoid returning too many chunks from the
# same page. Usually one strong chunk per page
# gives cleaner context to the LLM.

MAX_CHUNKS_PER_PAGE = 1


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

    The pipeline:

    1. Search Qdrant for candidate chunks
    2. Remove duplicate chunks
    3. Prefer chunks with valid page numbers
    4. Limit repeated chunks from the same page
    5. Return the best final results
    """

    # -----------------------------------------------------
    # STEP 1: SEARCH QDRANT
    # -----------------------------------------------------

    results = search_similar_chunks(
        query=query,
        user_id=user_id,
        limit=limit,
    )

    if not results:
        return []


    # -----------------------------------------------------
    # STEP 2: CONVERT RESULTS
    # -----------------------------------------------------

    candidates = []

    for result in results:
        payload = result.payload or {}

        candidates.append(
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


    # -----------------------------------------------------
    # STEP 3: REMOVE EXACT DUPLICATES
    #
    # Each chunk should normally have a unique
    # document_id + chunk_index combination.
    # -----------------------------------------------------

    seen_chunks = set()

    unique_candidates = []

    for chunk in candidates:

        chunk_key = (
            chunk["document_id"],
            chunk["chunk_index"],
        )

        if chunk_key in seen_chunks:
            continue

        seen_chunks.add(
            chunk_key
        )

        unique_candidates.append(
            chunk
        )


    # -----------------------------------------------------
    # STEP 4: SORT BY RELEVANCE
    #
    # Qdrant normally already returns sorted results,
    # but we explicitly sort to keep the retrieval
    # service predictable.
    # -----------------------------------------------------

    unique_candidates.sort(
        key=lambda chunk: chunk["score"],
        reverse=True,
    )


    # -----------------------------------------------------
    # STEP 5: PREFER VALID PAGE NUMBERS
    #
    # First use chunks that have page numbers.
    # If there are not enough, we can fall back
    # to chunks without page information.
    # -----------------------------------------------------

    chunks_with_pages = [
        chunk
        for chunk in unique_candidates
        if chunk["page_number"] is not None
    ]

    chunks_without_pages = [
        chunk
        for chunk in unique_candidates
        if chunk["page_number"] is None
    ]


    # -----------------------------------------------------
    # STEP 6: LIMIT CHUNKS PER PAGE
    #
    # Prevents multiple chunks from the same page
    # dominating the LLM context.
    # -----------------------------------------------------

    selected_chunks = []

    page_counts = {}


    def add_chunks(
        chunk_list,
        selected,
        counts,
        max_results,
    ):
        for chunk in chunk_list:

            if len(selected) >= max_results:
                break

            document_id = (
                chunk["document_id"]
            )

            page_number = (
                chunk["page_number"]
            )

            page_key = (
                document_id,
                page_number,
            )

            current_count = (
                counts.get(
                    page_key,
                    0,
                )
            )

            if (
                current_count
                >= MAX_CHUNKS_PER_PAGE
            ):
                continue

            selected.append(
                chunk
            )

            counts[page_key] = (
                current_count + 1
            )


    # -----------------------------------------------------
    # FIRST: ADD CHUNKS WITH PAGE NUMBERS
    # -----------------------------------------------------

    add_chunks(
        chunks_with_pages,
        selected_chunks,
        page_counts,
        limit,
    )


    # -----------------------------------------------------
    # SECOND: FALL BACK TO CHUNKS WITHOUT PAGE NUMBERS
    #
    # Only if we still need more context.
    # -----------------------------------------------------

    if len(selected_chunks) < limit:

        add_chunks(
            chunks_without_pages,
            selected_chunks,
            page_counts,
            limit,
        )


    # -----------------------------------------------------
    # STEP 7: RETURN FINAL CHUNKS
    # -----------------------------------------------------

    return selected_chunks