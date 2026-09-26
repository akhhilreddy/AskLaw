import re
import time
from collections.abc import Callable, Sequence
from typing import Any, Protocol

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
    VectorParams,
)

from app.core.config import settings


QDRANT_URL = settings.QDRANT_URL
COLLECTION_NAME = settings.QDRANT_COLLECTION_NAME
EMBEDDING_PROVIDER = settings.EMBEDDING_PROVIDER
EMBEDDING_MODEL = settings.EMBEDDING_MODEL

LOCAL_EMBEDDING_DIMENSION = 384
GEMINI_EMBEDDING_MODEL = "gemini-embedding-2"
GEMINI_EMBEDDING_DIMENSION = 3072
LOCAL_INDEXING_BATCH_SIZE = 64
GEMINI_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


qdrant_client = QdrantClient(
    url=QDRANT_URL,
    api_key=settings.qdrant_api_key,
    check_compatibility=False,
)


class NonRetryableEmbeddingError(RuntimeError):
    """Embedding failure that task-level retries cannot resolve."""


class EmbeddingProvider(Protocol):
    @property
    def dimension(self) -> int: ...

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


def _validate_embeddings(
    vectors: Sequence[Sequence[float]],
    *,
    expected_count: int,
    expected_dimension: int,
    provider_name: str,
) -> list[list[float]]:
    if len(vectors) != expected_count:
        raise NonRetryableEmbeddingError(
            f"{provider_name} returned {len(vectors)} embeddings for "
            f"{expected_count} inputs"
        )

    normalized: list[list[float]] = []

    for index, vector in enumerate(vectors):
        values = list(vector)
        if len(values) != expected_dimension:
            raise NonRetryableEmbeddingError(
                f"{provider_name} embedding {index} has dimension "
                f"{len(values)}; expected {expected_dimension}"
            )
        normalized.append(values)

    return normalized


class LocalEmbeddingProvider:
    """Lazy SentenceTransformer provider for the existing MiniLM path."""

    def __init__(
        self,
        model_name: str,
        *,
        model_factory: Callable[[str], Any] | None = None,
    ):
        self.model_name = model_name
        self._model_factory = model_factory
        self._model: Any | None = None

    def _get_model(self):
        if self._model is None:
            if self._model_factory is None:
                from sentence_transformers import SentenceTransformer

                self._model_factory = SentenceTransformer
            self._model = self._model_factory(self.model_name)
        return self._model

    @property
    def dimension(self) -> int:
        model = self._get_model()
        get_dimension = getattr(model, "get_embedding_dimension", None)
        if get_dimension is None:
            get_dimension = model.get_sentence_embedding_dimension
        dimension = int(get_dimension())
        if (
            self.model_name == "sentence-transformers/all-MiniLM-L6-v2"
            and dimension != LOCAL_EMBEDDING_DIMENSION
        ):
            raise NonRetryableEmbeddingError(
                f"Local MiniLM model reported dimension {dimension}; "
                f"expected {LOCAL_EMBEDDING_DIMENSION}"
            )
        return dimension

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []

        encoded = self._get_model().encode(list(texts))
        vectors = encoded.tolist() if hasattr(encoded, "tolist") else list(encoded)

        if vectors and isinstance(vectors[0], (int, float)):
            vectors = [vectors]

        return _validate_embeddings(
            vectors,
            expected_count=len(texts),
            expected_dimension=self.dimension,
            provider_name="Local embedding provider",
        )


def _is_daily_gemini_quota_error(exc: Exception) -> bool:
    details = getattr(exc, "details", None)
    if not isinstance(details, dict):
        return False

    error = details.get("error", details)
    if not isinstance(error, dict):
        return False

    for detail in error.get("details", []):
        if not isinstance(detail, dict):
            continue
        for violation in detail.get("violations", []):
            quota_id = violation.get("quotaId", "")
            if "PerDay" in quota_id:
                return True

    return False


def _is_transient_gemini_error(exc: Exception) -> bool:
    status_code = getattr(exc, "code", None)
    if status_code == 429 and _is_daily_gemini_quota_error(exc):
        return False
    if status_code in GEMINI_RETRYABLE_STATUS_CODES:
        return True

    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True

    try:
        import httpx

        return isinstance(exc, httpx.TransportError)
    except ImportError:
        return False


def _gemini_retry_delay_seconds(
    exc: Exception,
    fallback_seconds: float,
) -> float:
    """Honor Google RetryInfo when present, otherwise use local backoff."""

    details = getattr(exc, "details", None)
    if not isinstance(details, dict):
        return fallback_seconds

    error = details.get("error", details)
    if not isinstance(error, dict):
        return fallback_seconds

    for detail in error.get("details", []):
        if not isinstance(detail, dict):
            continue
        retry_delay = detail.get("retryDelay")
        if not isinstance(retry_delay, str):
            continue
        match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)s", retry_delay.strip())
        if match:
            return max(fallback_seconds, float(match.group(1)) + 1.0)

    return fallback_seconds


class GeminiEmbeddingProvider:
    """Google GenAI provider with bounded transient-error retries."""

    dimension = GEMINI_EMBEDDING_DIMENSION

    def __init__(
        self,
        api_key: str,
        *,
        client: Any | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        max_attempts: int = 5,
        retry_base_seconds: float = 1.0,
    ):
        if not api_key.strip():
            raise NonRetryableEmbeddingError(
                "GEMINI_API_KEY is required when EMBEDDING_PROVIDER=gemini"
            )
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")

        if client is None:
            from google import genai

            client = genai.Client(api_key=api_key)

        self._client = client
        self._sleeper = sleeper
        self._max_attempts = max_attempts
        self._retry_base_seconds = retry_base_seconds

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []

        from google.genai import types

        contents = [
            types.UserContent(parts=[types.Part(text=text)])
            for text in texts
        ]

        for attempt in range(1, self._max_attempts + 1):
            try:
                response = self._client.models.embed_content(
                    model=GEMINI_EMBEDDING_MODEL,
                    contents=contents,
                )
                embeddings = response.embeddings or []
                vectors = [embedding.values or [] for embedding in embeddings]
                return _validate_embeddings(
                    vectors,
                    expected_count=len(texts),
                    expected_dimension=self.dimension,
                    provider_name="Gemini embedding provider",
                )
            except Exception as exc:
                if isinstance(exc, NonRetryableEmbeddingError):
                    raise

                if (
                    attempt >= self._max_attempts
                    or not _is_transient_gemini_error(exc)
                ):
                    status_code = getattr(exc, "code", None)
                    if _is_daily_gemini_quota_error(exc):
                        raise NonRetryableEmbeddingError(
                            "Gemini daily embedding quota is exhausted; "
                            "retry after the quota resets or use a project "
                            "with sufficient quota"
                        ) from exc
                    if isinstance(status_code, int) and 400 <= status_code < 500:
                        raise NonRetryableEmbeddingError(
                            f"Gemini embedding request was rejected with "
                            f"HTTP {status_code}; check credentials and request "
                            "configuration"
                        ) from exc
                    raise
                fallback_seconds = (
                    self._retry_base_seconds * (2 ** (attempt - 1))
                )
                self._sleeper(
                    _gemini_retry_delay_seconds(exc, fallback_seconds)
                )

        raise NonRetryableEmbeddingError("Gemini embedding request failed")


_embedding_provider: EmbeddingProvider | None = None


def _get_embedding_provider() -> EmbeddingProvider:
    global _embedding_provider

    if _embedding_provider is None:
        if EMBEDDING_PROVIDER == "local":
            _embedding_provider = LocalEmbeddingProvider(EMBEDDING_MODEL)
        elif EMBEDDING_PROVIDER == "gemini":
            _embedding_provider = GeminiEmbeddingProvider(settings.GEMINI_API_KEY)
        else:
            raise NonRetryableEmbeddingError(
                f"Unsupported embedding provider: {EMBEDDING_PROVIDER}"
            )

    return _embedding_provider


def get_embedding_dimension() -> int:
    return _get_embedding_provider().dimension


def get_embedding_batch_size() -> int:
    if EMBEDDING_PROVIDER == "gemini":
        return settings.GEMINI_EMBEDDING_BATCH_SIZE
    return LOCAL_INDEXING_BATCH_SIZE


def _collection_vector_size(collection_info: Any) -> int:
    vectors = collection_info.config.params.vectors

    if hasattr(vectors, "size"):
        return int(vectors.size)

    if isinstance(vectors, dict) and len(vectors) == 1:
        vector_params = next(iter(vectors.values()))
        if hasattr(vector_params, "size"):
            return int(vector_params.size)

    raise NonRetryableEmbeddingError(
        f"Unable to determine vector size for Qdrant collection "
        f"'{COLLECTION_NAME}'. AskLaw expects a single unnamed vector."
    )


def create_collection() -> None:
    expected_dimension = get_embedding_dimension()
    collections = qdrant_client.get_collections()
    collection_names = {
        collection.name for collection in collections.collections
    }

    if COLLECTION_NAME in collection_names:
        actual_dimension = _collection_vector_size(
            qdrant_client.get_collection(COLLECTION_NAME)
        )
        if actual_dimension != expected_dimension:
            raise NonRetryableEmbeddingError(
                f"Qdrant collection '{COLLECTION_NAME}' has vector dimension "
                f"{actual_dimension}, but EMBEDDING_PROVIDER={EMBEDDING_PROVIDER} "
                f"requires {expected_dimension}. Configure a separate collection; "
                "AskLaw will not resize or recreate an existing collection."
            )
        return

    qdrant_client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(
            size=expected_dimension,
            distance=Distance.COSINE,
        ),
    )


def create_embeddings(texts: Sequence[str]) -> list[list[float]]:
    normalized_texts = [str(text) for text in texts]
    if not normalized_texts:
        return []

    provider = _get_embedding_provider()
    batch_size = get_embedding_batch_size()
    vectors: list[list[float]] = []

    for start in range(0, len(normalized_texts), batch_size):
        vectors.extend(
            provider.embed(normalized_texts[start : start + batch_size])
        )

    return _validate_embeddings(
        vectors,
        expected_count=len(normalized_texts),
        expected_dimension=provider.dimension,
        provider_name=f"{EMBEDDING_PROVIDER} embedding provider",
    )


def create_embedding(text: str) -> list[float]:
    """Backward-compatible single-text embedding API."""

    return create_embeddings([text])[0]


def store_chunks(chunks: Sequence[dict[str, Any]]) -> int:
    """Embed and upsert chunks in bounded batches, preserving payload scope."""

    valid_chunks = [chunk for chunk in chunks if chunk.get("text")]
    if not valid_chunks:
        return 0

    batch_size = get_embedding_batch_size()
    stored_count = 0

    for start in range(0, len(valid_chunks), batch_size):
        batch = valid_chunks[start : start + batch_size]
        vectors = create_embeddings([chunk["text"] for chunk in batch])
        points = [
            PointStruct(
                id=chunk["chunk_id"],
                vector=vector,
                payload={
                    "document_id": chunk["document_id"],
                    "user_id": chunk["user_id"],
                    "filename": chunk["filename"],
                    "chunk_index": chunk["chunk_index"],
                    "page_number": chunk["page_number"],
                    "text": chunk["text"],
                },
            )
            for chunk, vector in zip(batch, vectors, strict=True)
        ]
        qdrant_client.upsert(
            collection_name=COLLECTION_NAME,
            points=points,
            wait=True,
        )
        stored_count += len(points)

    return stored_count


def store_chunk(
    chunk_id,
    text,
    document_id,
    user_id,
    filename,
    chunk_index,
    page_number,
):
    """Backward-compatible single-chunk storage API."""

    store_chunks(
        [
            {
                "chunk_id": chunk_id,
                "text": text,
                "document_id": document_id,
                "user_id": user_id,
                "filename": filename,
                "chunk_index": chunk_index,
                "page_number": page_number,
            }
        ]
    )


def delete_document_chunks(
    document_id: str,
    user_id: str,
):
    """Delete vectors for one owned document, if the collection exists."""

    existing_collections = qdrant_client.get_collections()
    collection_names = {
        collection.name for collection in existing_collections.collections
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


def search_similar_chunks(
    query: str,
    user_id: str,
    limit: int = 5,
):
    query_vector = create_embedding(query)
    query_filter = Filter(
        must=[
            FieldCondition(
                key="user_id",
                match=MatchValue(value=user_id),
            )
        ]
    )
    response = qdrant_client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        query_filter=query_filter,
        limit=limit,
        with_payload=True,
    )
    return response.points
