import os
import sys
import types
import unittest
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "7")
os.environ.setdefault("GROQ_API_KEY", "test-groq-key")


class FakeEmbedding:
    def tolist(self):
        return [0.1, 0.2, 0.3]


class FakeSentenceTransformer:
    def __init__(self, _model_name):
        pass

    def encode(self, _text):
        return FakeEmbedding()

    def get_sentence_embedding_dimension(self):
        return 3


fake_sentence_transformers = types.ModuleType("sentence_transformers")
fake_sentence_transformers.SentenceTransformer = FakeSentenceTransformer
sys.modules.setdefault("sentence_transformers", fake_sentence_transformers)

from bson import ObjectId
from fastapi import HTTPException, Response

from app.schemas.auth import SignUpRequest, UserLogin
from app.schemas.chat import ChatMessage, ChatRequest
from app.services import claim_verifier, query_router, vector_service
from app.services import document_service, retrieval_service
from app.tasks import document_tasks


def tearDownModule():
    from app.db.mongodb import client

    client.close()


class FakeCollection:
    def __init__(self, document=None):
        self.document = document
        self.updates = []
        self.deleted_filters = []
        self.inserted = []

    def find_one(self, query, projection=None):
        if callable(self.document):
            return self.document(query, projection)
        return self.document

    def update_one(self, query, update):
        self.updates.append((query, update))
        return SimpleNamespace(matched_count=1, modified_count=1)

    def delete_one(self, query):
        self.deleted_filters.append(query)
        return SimpleNamespace(deleted_count=1 if self.document else 0)

    def insert_one(self, document):
        self.inserted.append(document)
        return SimpleNamespace(inserted_id=ObjectId())


class FakeCursor(list):
    def sort(self, _keys):
        return self


class DocumentServiceTests(unittest.TestCase):
    def setUp(self):
        self.document_id = str(ObjectId())
        self.user_id = str(ObjectId())

    def test_delete_is_scoped_to_owner_in_both_stores(self):
        collection = FakeCollection(
            {"_id": ObjectId(self.document_id), "filename": "law.pdf", "status": "indexed"}
        )
        cleanup = Mock()

        with patch.object(document_service, "document_collection", collection), patch.object(
            document_service, "delete_document_chunks", cleanup
        ):
            result = document_service.delete_owned_document(
                self.document_id, self.user_id
            )

        cleanup.assert_called_once_with(
            document_id=self.document_id, user_id=self.user_id
        )
        self.assertEqual(
            collection.deleted_filters[0],
            {"_id": ObjectId(self.document_id), "user_id": self.user_id},
        )
        self.assertEqual(result["document_id"], self.document_id)

    def test_delete_hides_missing_or_unowned_document(self):
        collection = FakeCollection(None)
        cleanup = Mock()

        with patch.object(document_service, "document_collection", collection), patch.object(
            document_service, "delete_document_chunks", cleanup
        ):
            result = document_service.delete_owned_document(
                self.document_id, self.user_id
            )

        self.assertIsNone(result)
        cleanup.assert_not_called()

    def test_delete_keeps_mongo_record_if_vector_cleanup_fails(self):
        collection = FakeCollection(
            {"_id": ObjectId(self.document_id), "filename": "law.pdf", "status": "failed"}
        )

        with patch.object(document_service, "document_collection", collection), patch.object(
            document_service,
            "delete_document_chunks",
            side_effect=RuntimeError("qdrant down"),
        ):
            with self.assertRaises(HTTPException) as caught:
                document_service.delete_owned_document(self.document_id, self.user_id)

        self.assertEqual(caught.exception.status_code, 502)
        self.assertEqual(collection.deleted_filters, [])

    def test_delete_rejects_in_flight_indexing(self):
        collection = FakeCollection(
            {"_id": ObjectId(self.document_id), "filename": "law.pdf", "status": "processing"}
        )

        with patch.object(document_service, "document_collection", collection):
            with self.assertRaises(HTTPException) as caught:
                document_service.delete_owned_document(self.document_id, self.user_id)

        self.assertEqual(caught.exception.status_code, 409)

    def test_page_chunking_preserves_page_metadata(self):
        chunks = document_service.create_page_chunks(
            "A" * 25, page_number=4, chunk_size=10, overlap=2
        )
        self.assertEqual([item["page_number"] for item in chunks], [4, 4, 4])
        self.assertEqual([len(item["text"]) for item in chunks], [10, 10, 9])

    def test_upload_persists_uploaded_status_and_queues_indexing(self):
        pages = [SimpleNamespace(extract_text=lambda: "Article 32 provides remedies.")]
        collection = FakeCollection()
        queued = SimpleNamespace(id="task-1")
        upload = SimpleNamespace(
            file=object(), filename="constitution.pdf", content_type="application/pdf"
        )

        with patch.object(
            document_service, "PdfReader", return_value=SimpleNamespace(pages=pages)
        ), patch.object(document_service, "document_collection", collection), patch.object(
            document_service.index_document, "delay", return_value=queued
        ):
            result = document_service.save_uploaded_document(upload, self.user_id)

        self.assertEqual(collection.inserted[0]["status"], "uploaded")
        self.assertEqual(collection.inserted[0]["user_id"], self.user_id)
        self.assertEqual(result["task_id"], "task-1")
        self.assertEqual(result["filename"], "constitution.pdf")

    def test_upload_endpoint_rejects_non_pdf_before_service_call(self):
        from app.api import document as document_api

        upload = SimpleNamespace(filename="notes.txt", content_type="text/plain")

        with patch.object(document_api, "save_uploaded_document") as save:
            with self.assertRaises(HTTPException) as caught:
                document_api.upload_document(
                    file=upload, current_user={"_id": ObjectId(self.user_id)}
                )

        self.assertEqual(caught.exception.status_code, 400)
        save.assert_not_called()

    def test_document_listing_is_user_scoped_and_omits_private_fields(self):
        document_id = ObjectId()
        captured = {}
        collection = Mock()
        collection.update_many.return_value = SimpleNamespace(modified_count=0)

        def find(query, projection):
            captured["query"] = query
            captured["projection"] = projection
            return FakeCursor(
                [
                    {
                        "_id": document_id,
                        "filename": "law.pdf",
                        "content_type": "application/pdf",
                        "content": "private document text",
                        "page_count": 2,
                        "chunk_count": 3,
                        "status": "indexed",
                        "filesystem_path": "/private/path.pdf",
                    }
                ]
            )

        collection.find.side_effect = find

        with patch.object(document_service, "document_collection", collection):
            documents = document_service.get_user_documents(self.user_id)

        self.assertEqual(captured["query"], {"user_id": self.user_id})
        self.assertEqual(documents[0]["document_id"], str(document_id))
        self.assertNotIn("content", documents[0])
        self.assertNotIn("filesystem_path", documents[0])


class QdrantIsolationTests(unittest.TestCase):
    def test_delete_filter_contains_user_and_document(self):
        captured = {}
        fake_client = Mock()
        fake_client.get_collections.return_value = SimpleNamespace(
            collections=[SimpleNamespace(name=vector_service.COLLECTION_NAME)]
        )
        fake_client.delete.side_effect = lambda **kwargs: captured.update(kwargs)

        with patch.object(vector_service, "qdrant_client", fake_client):
            vector_service.delete_document_chunks("doc-1", "user-1")

        conditions = captured["points_selector"].filter.must
        self.assertEqual(
            {(item.key, item.match.value) for item in conditions},
            {("document_id", "doc-1"), ("user_id", "user-1")},
        )
        self.assertTrue(captured["wait"])

    def test_document_semantic_search_uses_both_scope_filters(self):
        captured = {}
        fake_client = Mock()

        def query_points(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(points=[])

        fake_client.query_points.side_effect = query_points

        with patch.object(retrieval_service, "qdrant_client", fake_client), patch.object(
            retrieval_service, "create_embedding", return_value=[0.1, 0.2]
        ):
            retrieval_service.semantic_search(
                "Article 32", "user-1", 5, document_id="doc-1"
            )

        conditions = captured["query_filter"].must
        self.assertEqual(
            {(item.key, item.match.value) for item in conditions},
            {("document_id", "doc-1"), ("user_id", "user-1")},
        )

    def test_normal_semantic_search_remains_user_scoped(self):
        captured = {}
        fake_client = Mock()
        fake_client.query_points.side_effect = lambda **kwargs: (
            captured.update(kwargs) or SimpleNamespace(points=[])
        )

        with patch.object(retrieval_service, "qdrant_client", fake_client), patch.object(
            retrieval_service, "create_embedding", return_value=[0.1, 0.2]
        ):
            retrieval_service.semantic_search("constitutional remedy", "user-1", 5)

        conditions = captured["query_filter"].must
        self.assertEqual(
            {(item.key, item.match.value) for item in conditions},
            {("user_id", "user-1")},
        )

    def test_exact_article_scan_is_document_and_user_scoped(self):
        captured = {}
        point = SimpleNamespace(
            payload={
                "document_id": "doc-1",
                "user_id": "user-1",
                "filename": "constitution.pdf",
                "chunk_index": 4,
                "page_number": 2,
                "text": (
                    "32. Remedies for enforcement of rights conferred by this Part. "
                    "(1) The right to move the Supreme Court by appropriate proceedings "
                    "for the enforcement of the rights conferred by this Part is guaranteed."
                ),
            }
        )
        fake_client = Mock()

        def scroll(**kwargs):
            captured.update(kwargs)
            return [point], None

        fake_client.scroll.side_effect = scroll

        with patch.object(retrieval_service, "qdrant_client", fake_client):
            results = retrieval_service.find_exact_article(
                "32", "user-1", document_id="doc-1"
            )

        conditions = captured["scroll_filter"].must
        self.assertEqual(
            {(item.key, item.match.value) for item in conditions},
            {("document_id", "doc-1"), ("user_id", "user-1")},
        )
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["article_match"])


class IndexingLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.document_id = str(ObjectId())
        self.document = {
            "_id": ObjectId(self.document_id),
            "filename": "law.pdf",
            "chunks": [{"index": 0, "text": "Article 32", "page_number": 1}],
        }

    def test_success_sets_processing_then_indexed_and_payload_scope(self):
        collection = FakeCollection(self.document)
        store = Mock()

        with patch.object(document_tasks, "document_collection", collection), patch.object(
            document_tasks, "create_collection"
        ), patch.object(document_tasks, "store_chunk", store):
            result = document_tasks.index_document.run(self.document_id, "user-1")

        statuses = [update["$set"]["status"] for _, update in collection.updates]
        self.assertEqual(statuses, ["processing", "indexed"])
        self.assertEqual(result["chunks_indexed"], 1)
        self.assertEqual(store.call_args.kwargs["document_id"], self.document_id)
        self.assertEqual(store.call_args.kwargs["user_id"], "user-1")

    def test_final_failure_sets_failed(self):
        collection = FakeCollection(self.document)
        old_max_retries = document_tasks.index_document.max_retries
        document_tasks.index_document.max_retries = 0

        try:
            with patch.object(document_tasks, "document_collection", collection), patch.object(
                document_tasks, "create_collection", side_effect=RuntimeError("qdrant down")
            ), patch.object(document_tasks.logger, "exception"):
                with self.assertRaises(RuntimeError):
                    document_tasks.index_document.run(self.document_id, "user-1")
        finally:
            document_tasks.index_document.max_retries = old_max_retries

        statuses = [update["$set"]["status"] for _, update in collection.updates]
        self.assertEqual(statuses, ["processing", "failed"])


class AuthAndChatTests(unittest.TestCase):
    def test_signup_login_refresh_and_unauthorized_dependency(self):
        from app.api import auth
        from app.core import dependencies

        users = FakeCollection({"_id": ObjectId(), "email": "person@example.com", "password_hash": "hash"})

        with patch.object(auth, "user_collection", users), patch.object(
            auth, "verify_password", return_value=True
        ), patch.object(auth, "create_access_token", return_value="access"), patch.object(
            auth, "create_refresh_token", return_value="refresh"
        ):
            login_result = auth.login(
                UserLogin(email="person@example.com", password="secret"), Response()
            )
            self.assertEqual(login_result["access_token"], "access")

        empty_users = FakeCollection(None)
        with patch.object(auth, "user_collection", empty_users), patch.object(
            auth, "hash_password", return_value="hashed"
        ):
            signup_result = auth.signup(
                SignUpRequest(name="Person", email="new@example.com", password="secret")
            )
            self.assertEqual(signup_result["message"], "User registered successfully")
            self.assertNotIn("password", empty_users.inserted[0])
            self.assertEqual(empty_users.inserted[0]["password_hash"], "hashed")

        with patch.object(auth, "user_collection", users), patch.object(
            auth.jwt, "decode", return_value={"sub": "person@example.com"}
        ), patch.object(auth, "create_access_token", return_value="renewed"):
            self.assertEqual(auth.refresh_access_token("refresh")["access_token"], "renewed")

        with patch.object(dependencies.jwt, "decode", side_effect=dependencies.JWTError()):
            with self.assertRaises(HTTPException) as caught:
                dependencies.get_current_user("bad-token")
        self.assertEqual(caught.exception.status_code, 401)

    def test_refresh_cookie_attributes_match_login_and_logout(self):
        from app.api import auth

        users = FakeCollection(
            {"_id": ObjectId(), "email": "person@example.com", "password_hash": "hash"}
        )
        login_response = Response()

        with patch.object(auth, "user_collection", users), patch.object(
            auth, "verify_password", return_value=True
        ), patch.object(auth, "create_access_token", return_value="access"), patch.object(
            auth, "create_refresh_token", return_value="refresh"
        ):
            auth.login(
                UserLogin(email="person@example.com", password="secret"),
                login_response,
            )

        cookie = login_response.headers["set-cookie"]
        self.assertIn("refresh_token=refresh", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("Path=/auth", cookie)
        self.assertIn("SameSite=lax", cookie)
        self.assertIn("Max-Age=604800", cookie)
        self.assertIn("expires=", cookie.lower())
        self.assertNotIn("Secure", cookie)

        logout_response = Response()
        auth.logout(logout_response)
        deleted_cookie = logout_response.headers["set-cookie"]
        self.assertIn("refresh_token=", deleted_cookie)
        self.assertIn("Max-Age=0", deleted_cookie)
        self.assertIn("Path=/auth", deleted_cookie)

    def test_refresh_rejects_missing_invalid_and_deleted_user_sessions(self):
        from app.api import auth

        with self.assertRaises(HTTPException) as missing:
            auth.refresh_access_token(None)
        self.assertEqual(missing.exception.status_code, 401)

        with patch.object(auth.jwt, "decode", side_effect=auth.JWTError()):
            with self.assertRaises(HTTPException) as invalid:
                auth.refresh_access_token("invalid")
        self.assertEqual(invalid.exception.status_code, 401)

        with patch.object(
            auth.jwt, "decode", return_value={"sub": "deleted@example.com"}
        ), patch.object(auth, "user_collection", FakeCollection(None)):
            with self.assertRaises(HTTPException) as deleted:
                auth.refresh_access_token("refresh")
        self.assertEqual(deleted.exception.status_code, 401)

        with patch.object(
            auth.jwt,
            "decode",
            return_value={"sub": "person@example.com", "token_type": "access"},
        ), patch.object(auth, "user_collection", FakeCollection({"email": "person@example.com"})):
            with self.assertRaises(HTTPException) as wrong_type:
                auth.refresh_access_token("access-token")
        self.assertEqual(wrong_type.exception.status_code, 401)

    def test_access_and_refresh_token_lifetimes(self):
        from jose import jwt

        from app.core.config import settings
        from app.utils.security import create_access_token, create_refresh_token

        now = datetime.now(timezone.utc).timestamp()
        access_payload = jwt.decode(
            create_access_token({"sub": "person@example.com"}),
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        refresh_payload = jwt.decode(
            create_refresh_token({"sub": "person@example.com"}),
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )

        self.assertAlmostEqual(
            access_payload["exp"] - now,
            settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            delta=3,
        )
        self.assertAlmostEqual(
            refresh_payload["exp"] - now,
            settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
            delta=3,
        )
        self.assertGreater(refresh_payload["exp"], access_payload["exp"])
        self.assertEqual(access_payload["token_type"], "access")
        self.assertEqual(refresh_payload["token_type"], "refresh")

    def test_refresh_token_cannot_authenticate_protected_endpoint(self):
        from app.core import dependencies

        payload = {"sub": "person@example.com", "token_type": "refresh"}

        with patch.object(dependencies.jwt, "decode", return_value=payload):
            with self.assertRaises(HTTPException) as caught:
                dependencies.get_current_user("refresh-token")

        self.assertEqual(caught.exception.status_code, 401)

    def test_chat_request_document_id_is_optional(self):
        normal = ChatRequest(messages=[ChatMessage(role="user", content="Hello")])
        scoped = ChatRequest(
            messages=[ChatMessage(role="user", content="Article 32")],
            document_id="doc-1",
        )
        self.assertIsNone(normal.document_id)
        self.assertEqual(scoped.document_id, "doc-1")

    def test_chat_rejects_unowned_and_non_ready_documents(self):
        from app.api import chat

        request = ChatRequest(
            messages=[ChatMessage(role="user", content="Article 32")],
            document_id=str(ObjectId()),
        )
        current_user = {"_id": ObjectId()}

        with patch.object(chat, "get_owned_document", return_value=None):
            with self.assertRaises(HTTPException) as missing:
                chat.chat_stream(request, current_user)
        self.assertEqual(missing.exception.status_code, 404)

        with patch.object(
            chat, "get_owned_document", return_value={"status": "processing"}
        ):
            with self.assertRaises(HTTPException) as processing:
                chat.chat_stream(request, current_user)
        self.assertEqual(processing.exception.status_code, 409)

    def test_stream_emits_verification_route_and_document_scope(self):
        from app.services import ai_service

        retrieval = AsyncMock(
            return_value={"route": "rag", "rag_results": [], "web_results": []}
        )
        stream_chunk = SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content="Supported answer."))]
        )
        client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=Mock(return_value=[stream_chunk]))
            )
        )
        report = {
            "claims": [{"claim_id": "claim-1", "claim": "Supported answer.", "support": "supported"}],
            "summary": {
                "total_claims": 1,
                "supported_claims": 1,
                "partial_claims": 0,
                "unsupported_claims": 0,
                "legal_claims": 0,
            },
        }

        with patch.object(ai_service, "retrieve_for_query", retrieval), patch.object(
            ai_service,
            "build_evidence_bundle",
            return_value={"evidence": [], "counts": {}},
        ), patch.object(ai_service, "build_legal_prompt", return_value="prompt"), patch.object(
            ai_service, "client", client
        ), patch.object(ai_service, "verify_claims", return_value=report), patch.object(
            ai_service, "calculate_grounding_score", return_value=1.0
        ):
            events = [
                json.loads(item)
                for item in ai_service.stream_response(
                    [ChatMessage(role="user", content="Article 32")],
                    user_id="user-1",
                    document_id="doc-1",
                )
            ]

        retrieval.assert_awaited_once_with(
            query="Article 32", user_id="user-1", document_id="doc-1"
        )
        verification = next(item for item in events if item["type"] == "verification")
        route = next(item for item in events if item["type"] == "route")
        self.assertEqual(verification["grounding_score"], 1.0)
        self.assertEqual(len(verification["claims"]), 1)
        self.assertEqual(route["route"], "rag")


class RoutingAndVerificationTests(unittest.TestCase):
    def test_rag_web_and_hybrid_routes(self):
        self.assertEqual(query_router.route_query("What does Article 32 say?").value, "rag")
        self.assertEqual(query_router.route_query("Latest privacy judgment").value, "web")
        self.assertEqual(
            query_router.route_query("Latest development about Article 32").value,
            "hybrid",
        )

    def test_verification_report_and_grounding_score(self):
        report = claim_verifier.verify_claims(
            "Article 32 provides constitutional remedies.",
            [{"evidence_id": "e1", "title": "Article 32", "text": "Article 32 provides constitutional remedies."}],
        )
        score = claim_verifier.calculate_grounding_score(report)
        self.assertEqual(report["summary"]["total_claims"], 1)
        self.assertEqual(report["claims"][0]["support"], "supported")
        self.assertEqual(score, 1.0)

        unsupported = claim_verifier.verify_claims(
            "Article 99 guarantees an unlimited remedy.", []
        )
        self.assertEqual(unsupported["claims"][0]["support"], "unsupported")


if __name__ == "__main__":
    unittest.main()
