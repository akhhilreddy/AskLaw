import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from google.genai.errors import ClientError, ServerError
from pydantic import ValidationError


os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "7")
os.environ.setdefault("GROQ_API_KEY", "test-groq-key")


from app.services import retrieval_service, vector_service
from app.core.config import Settings


def make_vector(marker: float, dimension: int) -> list[float]:
    return [marker, *([0.0] * (dimension - 1))]


class FakeLocalModel:
    def get_sentence_embedding_dimension(self):
        return vector_service.LOCAL_EMBEDDING_DIMENSION

    def encode(self, texts):
        return [
            make_vector(float(index), vector_service.LOCAL_EMBEDDING_DIMENSION)
            for index, _text in enumerate(texts)
        ]


class FakeGeminiModels:
    def __init__(self, effects=None):
        self.effects = list(effects or [])
        self.calls = []

    def embed_content(self, *, model, contents):
        self.calls.append({"model": model, "contents": contents})
        if self.effects:
            effect = self.effects.pop(0)
            if isinstance(effect, Exception):
                raise effect
            return effect
        return SimpleNamespace(
            embeddings=[
                SimpleNamespace(
                    values=make_vector(
                        float(index), vector_service.GEMINI_EMBEDDING_DIMENSION
                    )
                )
                for index, _text in enumerate(contents)
            ]
        )


class EmbeddingProviderTests(unittest.TestCase):
    def test_gemini_settings_require_api_key(self):
        with self.assertRaisesRegex(ValidationError, "GEMINI_API_KEY"):
            Settings(
                SECRET_KEY="test-secret-key",
                ALGORITHM="HS256",
                ACCESS_TOKEN_EXPIRE_MINUTES=15,
                REFRESH_TOKEN_EXPIRE_DAYS=7,
                EMBEDDING_PROVIDER="gemini",
                GEMINI_API_KEY="",
                _env_file=None,
            )

    def test_local_provider_returns_384_dimensions_in_order(self):
        provider = vector_service.LocalEmbeddingProvider(
            "sentence-transformers/all-MiniLM-L6-v2",
            model_factory=lambda _name: FakeLocalModel(),
        )

        vectors = provider.embed(["first", "second"])

        self.assertEqual([len(vector) for vector in vectors], [384, 384])
        self.assertEqual([vector[0] for vector in vectors], [0.0, 1.0])

    def test_gemini_provider_returns_3072_dimensions_in_order(self):
        models = FakeGeminiModels()
        provider = vector_service.GeminiEmbeddingProvider(
            "test-key",
            client=SimpleNamespace(models=models),
        )

        vectors = provider.embed(["first", "second"])

        self.assertEqual([len(vector) for vector in vectors], [3072, 3072])
        self.assertEqual([vector[0] for vector in vectors], [0.0, 1.0])
        self.assertEqual(
            [
                content.parts[0].text
                for content in models.calls[0]["contents"]
            ],
            ["first", "second"],
        )
        self.assertEqual(
            models.calls[0]["model"], vector_service.GEMINI_EMBEDDING_MODEL
        )

    def test_missing_gemini_api_key_fails_clearly(self):
        with self.assertRaisesRegex(RuntimeError, "GEMINI_API_KEY"):
            vector_service.GeminiEmbeddingProvider(" ")

    def test_gemini_embedding_count_mismatch_fails(self):
        models = FakeGeminiModels(
            effects=[SimpleNamespace(embeddings=[])]
        )
        provider = vector_service.GeminiEmbeddingProvider(
            "test-key",
            client=SimpleNamespace(models=models),
        )

        with self.assertRaisesRegex(RuntimeError, "0 embeddings for 1 inputs"):
            provider.embed(["one"])

    def test_transient_gemini_failure_retries_with_backoff(self):
        success = SimpleNamespace(
            embeddings=[
                SimpleNamespace(
                    values=make_vector(
                        1.0, vector_service.GEMINI_EMBEDDING_DIMENSION
                    )
                )
            ]
        )
        models = FakeGeminiModels(
            effects=[ServerError(503, {"message": "temporary"}), success]
        )
        sleeper = Mock()
        provider = vector_service.GeminiEmbeddingProvider(
            "test-key",
            client=SimpleNamespace(models=models),
            sleeper=sleeper,
            retry_base_seconds=0.25,
        )

        vectors = provider.embed(["retry me"])

        self.assertEqual(len(vectors), 1)
        self.assertEqual(len(models.calls), 2)
        sleeper.assert_called_once_with(0.25)

    def test_permanent_gemini_failure_is_not_retried(self):
        models = FakeGeminiModels(
            effects=[ClientError(401, {"message": "bad key"})]
        )
        sleeper = Mock()
        provider = vector_service.GeminiEmbeddingProvider(
            "test-key",
            client=SimpleNamespace(models=models),
            sleeper=sleeper,
        )

        with self.assertRaisesRegex(
            vector_service.NonRetryableEmbeddingError,
            "HTTP 401",
        ):
            provider.embed(["do not retry"])

        self.assertEqual(len(models.calls), 1)
        sleeper.assert_not_called()

    def test_gemini_rate_limit_honors_server_retry_delay(self):
        success = SimpleNamespace(
            embeddings=[
                SimpleNamespace(
                    values=make_vector(
                        1.0, vector_service.GEMINI_EMBEDDING_DIMENSION
                    )
                )
            ]
        )
        rate_limit = ClientError(
            429,
            {
                "error": {
                    "message": "quota",
                    "details": [{"retryDelay": "12.5s"}],
                }
            },
        )
        models = FakeGeminiModels(effects=[rate_limit, success])
        sleeper = Mock()
        provider = vector_service.GeminiEmbeddingProvider(
            "test-key",
            client=SimpleNamespace(models=models),
            sleeper=sleeper,
            max_attempts=2,
        )

        provider.embed(["wait for quota"])

        sleeper.assert_called_once_with(13.5)

    def test_gemini_daily_quota_failure_is_not_retried(self):
        daily_limit = ClientError(
            429,
            {
                "error": {
                    "message": "daily quota",
                    "details": [
                        {
                            "violations": [
                                {
                                    "quotaId": (
                                        "EmbedContentRequestsPerDayPerUser"
                                        "PerProjectPerModel-FreeTier"
                                    )
                                }
                            ],
                            "retryDelay": "58s",
                        }
                    ],
                }
            },
        )
        models = FakeGeminiModels(effects=[daily_limit])
        sleeper = Mock()
        provider = vector_service.GeminiEmbeddingProvider(
            "test-key",
            client=SimpleNamespace(models=models),
            sleeper=sleeper,
        )

        with self.assertRaisesRegex(
            vector_service.NonRetryableEmbeddingError,
            "daily embedding quota",
        ):
            provider.embed(["quota exhausted"])

        self.assertEqual(len(models.calls), 1)
        sleeper.assert_not_called()


class CollectionSafetyTests(unittest.TestCase):
    def test_collection_creation_uses_provider_dimension(self):
        client = Mock()
        client.get_collections.return_value = SimpleNamespace(collections=[])
        provider = SimpleNamespace(dimension=3072)

        with patch.object(vector_service, "qdrant_client", client), patch.object(
            vector_service, "_embedding_provider", provider
        ):
            vector_service.create_collection()

        vector_params = client.create_collection.call_args.kwargs["vectors_config"]
        self.assertEqual(vector_params.size, 3072)

    def test_wrong_dimension_collection_fails_without_recreation(self):
        client = Mock()
        client.get_collections.return_value = SimpleNamespace(
            collections=[SimpleNamespace(name=vector_service.COLLECTION_NAME)]
        )
        client.get_collection.return_value = SimpleNamespace(
            config=SimpleNamespace(
                params=SimpleNamespace(vectors=SimpleNamespace(size=384))
            )
        )
        provider = SimpleNamespace(dimension=3072)

        with patch.object(vector_service, "qdrant_client", client), patch.object(
            vector_service, "_embedding_provider", provider
        ):
            with self.assertRaisesRegex(RuntimeError, "separate collection"):
                vector_service.create_collection()

        client.create_collection.assert_not_called()
        client.delete_collection.assert_not_called()


class BatchIndexingAndRetrievalTests(unittest.TestCase):
    def test_store_chunks_embeds_and_upserts_in_batches(self):
        provider = Mock()
        provider.dimension = vector_service.GEMINI_EMBEDDING_DIMENSION
        provider.embed.side_effect = lambda texts: [
            make_vector(float(index), vector_service.GEMINI_EMBEDDING_DIMENSION)
            for index, _text in enumerate(texts)
        ]
        client = Mock()
        chunks = [
            {
                "chunk_id": f"point-{index}",
                "text": f"text-{index}",
                "document_id": "doc-1",
                "user_id": "user-1",
                "filename": "law.pdf",
                "chunk_index": index,
                "page_number": 1,
            }
            for index in range(3)
        ]

        with patch.object(vector_service, "EMBEDDING_PROVIDER", "gemini"), patch.object(
            vector_service.settings, "GEMINI_EMBEDDING_BATCH_SIZE", 2
        ), patch.object(
            vector_service, "_embedding_provider", provider
        ), patch.object(vector_service, "qdrant_client", client):
            stored = vector_service.store_chunks(chunks)

        self.assertEqual(stored, 3)
        self.assertEqual(provider.embed.call_count, 2)
        self.assertEqual(client.upsert.call_count, 2)
        self.assertEqual(
            sum(
                len(call.kwargs["points"])
                for call in client.upsert.call_args_list
            ),
            3,
        )
        for call in client.upsert.call_args_list:
            self.assertTrue(call.kwargs["wait"])
            for point in call.kwargs["points"]:
                self.assertEqual(point.payload["user_id"], "user-1")
                self.assertEqual(point.payload["document_id"], "doc-1")

    def test_retrieval_uses_selected_provider_and_preserves_user_scope(self):
        provider = Mock()
        provider.dimension = vector_service.GEMINI_EMBEDDING_DIMENSION
        provider.embed.return_value = [
            make_vector(1.0, vector_service.GEMINI_EMBEDDING_DIMENSION)
        ]
        client = Mock()
        client.query_points.return_value = SimpleNamespace(points=[])

        with patch.object(vector_service, "EMBEDDING_PROVIDER", "gemini"), patch.object(
            vector_service, "_embedding_provider", provider
        ), patch.object(
            retrieval_service,
            "create_embedding",
            side_effect=vector_service.create_embedding,
        ), patch.object(retrieval_service, "qdrant_client", client):
            retrieval_service.semantic_search(
                "What powers does Article 32 provide?",
                "user-1",
                5,
                document_id="doc-1",
            )

        provider.embed.assert_called_once_with([
            "What powers does Article 32 provide?"
        ])
        query = client.query_points.call_args.kwargs
        self.assertEqual(query["collection_name"], vector_service.COLLECTION_NAME)
        self.assertEqual(
            {(condition.key, condition.match.value) for condition in query["query_filter"].must},
            {("user_id", "user-1"), ("document_id", "doc-1")},
        )


if __name__ == "__main__":
    unittest.main()
