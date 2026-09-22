from qdrant_client import QdrantClient

from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    FilterSelector,
    MatchValue,
)

from sentence_transformers import (
    SentenceTransformer,
)

from app.core.config import settings


# =========================================================
# CONFIG
# =========================================================

QDRANT_URL = (
    settings.QDRANT_URL
)

COLLECTION_NAME = (
    settings.QDRANT_COLLECTION_NAME
)

EMBEDDING_MODEL = (
    settings.EMBEDDING_MODEL
)


# =========================================================
# RETRIEVAL SETTINGS
# =========================================================

# Minimum similarity score required
# for a chunk to be considered relevant.




# =========================================================
# CLIENT
# =========================================================

qdrant_client = QdrantClient(
    url=QDRANT_URL,
    check_compatibility=False,
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
# DELETE ONE USER'S DOCUMENT CHUNKS
# =========================================================

def delete_document_chunks(
    document_id: str,
    user_id: str,
):
    """Delete vectors for one owned document, if the collection exists."""

    existing_collections = qdrant_client.get_collections()
    collection_names = {
        collection.name
        for collection in existing_collections.collections
    }

    if COLLECTION_NAME not in collection_names:
        return

    qdrant_client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=FilterSelector(
            filter=Filter(
                must=[
                    FieldCondition(
                        key="document_id",
                        match=MatchValue(value=document_id),
                    ),
                    FieldCondition(
                        key="user_id",
                        match=MatchValue(value=user_id),
                    ),
                ]
            )
        ),
        wait=True,
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

    candidate_limit = limit


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


    
    return results
