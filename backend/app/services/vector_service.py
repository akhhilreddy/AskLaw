from qdrant_client import QdrantClient

from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)

from sentence_transformers import (
    SentenceTransformer,
)


# =========================================================
# CONFIG
# =========================================================

QDRANT_URL = (
    "http://localhost:6333"
)

COLLECTION_NAME = (
    "asklaw_documents"
)

EMBEDDING_MODEL = (
    "sentence-transformers/all-MiniLM-L6-v2"
)


# =========================================================
# RETRIEVAL SETTINGS
# =========================================================

# Minimum similarity score required
# for a chunk to be considered relevant.

MIN_SCORE = 0.35


# =========================================================
# CLIENT
# =========================================================

qdrant_client = QdrantClient(
    url=QDRANT_URL
)


# =========================================================
# EMBEDDING MODEL
# =========================================================

embedding_model = SentenceTransformer(
    EMBEDDING_MODEL
)


# =========================================================
# CREATE COLLECTION
# =========================================================

def create_collection():

    existing_collections = (
        qdrant_client.get_collections()
    )

    collection_names = [
        collection.name
        for collection in
        existing_collections.collections
    ]

    if COLLECTION_NAME in collection_names:
        return

    vector_size = (
        embedding_model
        .get_sentence_embedding_dimension()
    )

    qdrant_client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(
            size=vector_size,
            distance=Distance.COSINE,
        ),
    )


# =========================================================
# CREATE EMBEDDING
# =========================================================

def create_embedding(
    text: str,
):

    embedding = (
        embedding_model.encode(
            text
        )
    )

    return embedding.tolist()


# =========================================================
# STORE CHUNK IN QDRANT
# =========================================================

def store_chunk(
    chunk_id,
    text,
    document_id,
    user_id,
    filename,
    chunk_index,
    page_number,
):

    vector = create_embedding(
        text
    )

    point = PointStruct(
        id=chunk_id,
        vector=vector,
        payload={
            "document_id": document_id,
            "user_id": user_id,
            "filename": filename,
            "chunk_index": chunk_index,
            "page_number": page_number,
            "text": text,
        },
    )

    qdrant_client.upsert(
        collection_name=COLLECTION_NAME,
        points=[point],
    )


# =========================================================
# SEARCH SIMILAR CHUNKS
# =========================================================

def search_similar_chunks(
    query: str,
    user_id: str,
    limit: int = 5,
):

    # -----------------------------------------------------
    # CREATE QUERY EMBEDDING
    # -----------------------------------------------------

    query_vector = (
        create_embedding(
            query
        )
    )


    # -----------------------------------------------------
    # BUILD USER FILTER
    #
    # Users should only retrieve chunks
    # belonging to their own documents.
    # -----------------------------------------------------

    query_filter = Filter(
        must=[
            FieldCondition(
                key="user_id",
                match=MatchValue(
                    value=user_id
                ),
            )
        ]
    )


    # -----------------------------------------------------
    # SEARCH MORE RESULTS THAN WE NEED
    #
    # Example:
    # If we ultimately need 5 chunks,
    # retrieve 15 candidates first.
    # This gives us room to remove
    # weak or duplicate results later.
    # -----------------------------------------------------

    candidate_limit = (
        limit * 3
    )


    # -----------------------------------------------------
    # SEARCH QDRANT
    # -----------------------------------------------------

    response = (
        qdrant_client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            query_filter=query_filter,
            limit=candidate_limit,
            with_payload=True,
        )
    )

    results = response.points


    # -----------------------------------------------------
    # FILTER WEAK RESULTS
    # -----------------------------------------------------

    strong_results = [
        result
        for result in results
        if result.score >= MIN_SCORE
    ]


    # -----------------------------------------------------
    # FALLBACK
    #
    # If the threshold removes everything,
    # return the best available result.
    # This prevents the system from
    # unnecessarily saying that no
    # documents were found.
    # -----------------------------------------------------

    if not strong_results and results:

        strong_results = [
            results[0]
        ]


    # -----------------------------------------------------
    # RETURN CANDIDATES
    #
    # Do NOT cut to `limit` here yet.
    # retrieval_service will perform
    # deduplication and final selection.
    # -----------------------------------------------------

    return strong_results