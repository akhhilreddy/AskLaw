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
    Retrieve relevant legal document chunks
    and build the grounded prompt for the LLM.
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
        return None, []

    # -----------------------------------------------------
    # STEP 3: BUILD GROUNDED PROMPT
    # -----------------------------------------------------

    prompt = build_legal_prompt(
        query=query,
        retrieved_chunks=chunks,
    )

    return prompt, chunks