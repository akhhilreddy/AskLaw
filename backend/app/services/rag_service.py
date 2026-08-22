from app.services.retrieval_service import (
    retrieve_relevant_chunks,
)

from app.services.prompt_service import (
    build_legal_prompt,
)


# =========================================================
# BUILD RAG PROMPT
# =========================================================

def build_rag_prompt(
    query: str,
    user_id: str,
    limit: int = 5,
):
    """
    Retrieve relevant legal document chunks,
    build the grounded prompt for the LLM,
    and return the source metadata.
    """

    # -----------------------------------------------------
    # STEP 1: RETRIEVE RELEVANT CHUNKS
    # -----------------------------------------------------

    chunks = retrieve_relevant_chunks(
        query=query,
        user_id=user_id,
        limit=limit,
    )

    # -----------------------------------------------------
    # STEP 2: HANDLE NO RESULTS
    # -----------------------------------------------------

    if not chunks:
        return {
            "prompt": None,
            "sources": [],
        }

    # -----------------------------------------------------
    # STEP 3: BUILD GROUNDED PROMPT
    # -----------------------------------------------------

    prompt = build_legal_prompt(
        query=query,
        retrieved_chunks=chunks,
    )

    # -----------------------------------------------------
    # STEP 4: RETURN PROMPT + SOURCE METADATA
    # -----------------------------------------------------

    return {
        "prompt": prompt,
        "sources": chunks,
    }