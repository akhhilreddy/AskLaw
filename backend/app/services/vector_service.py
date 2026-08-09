from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
)

from sentence_transformers import SentenceTransformer


# =========================================================
# CONFIG
# =========================================================

QDRANT_URL = "http://localhost:6333"

COLLECTION_NAME = "asklaw_documents"

EMBEDDING_MODEL = (
    "sentence-transformers/all-MiniLM-L6-v2"
)


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
        for collection in existing_collections.collections
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

def create_embedding(text: str):
    embedding = embedding_model.encode(
        text
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
    vector = create_embedding(text)

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
    limit: int = 3,
):
    # Convert the user's question into an embedding
    query_vector = create_embedding(
        query
    )

    # Search Qdrant for the closest vectors
    results = qdrant_client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        query_filter={
            "must": [
                {
                    "key": "user_id",
                    "match": {
                        "value": user_id,
                    },
                }
            ]
        },
        limit=limit,
        with_payload=True,
    )

    return results.points