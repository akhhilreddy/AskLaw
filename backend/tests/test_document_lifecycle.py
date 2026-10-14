import os
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "7")
from bson import ObjectId
from app.services import document_lifecycle, retrieval_service
from app.tasks import document_tasks


class DocumentLeaseTests(unittest.TestCase):
    def test_readiness_query_requires_owner_and_ready_status(self):
        collection = Mock()
        identifier = ObjectId()
        collection.find.return_value = [{"_id": identifier}]
        ids = document_lifecycle.get_ready_document_ids(collection, "owner", str(identifier))
        self.assertEqual(ids, [str(identifier)])
        query = collection.find.call_args.args[0]
        self.assertEqual(query["user_id"], "owner")
        self.assertEqual(query["_id"], identifier)
        self.assertEqual(query["status"], {"$in": ["indexed", "ready"]})

    def test_no_ready_documents_skip_qdrant_and_embedding(self):
        with patch.object(retrieval_service, "ready_document_ids", return_value=[]), patch.object(retrieval_service, "qdrant_client") as qdrant, patch.object(retrieval_service, "create_embedding") as embed:
            self.assertEqual(retrieval_service.semantic_search("law", "owner", 5), [])
            self.assertEqual(retrieval_service.find_exact_article("32", "owner"), [])
        qdrant.query_points.assert_not_called()
        qdrant.scroll.assert_not_called()
        embed.assert_not_called()

    def test_qdrant_query_includes_ready_document_allowlist(self):
        client = Mock()
        client.query_points.return_value = SimpleNamespace(points=[])
        with patch.object(retrieval_service, "ready_document_ids", return_value=["ready-doc"]), patch.object(retrieval_service, "qdrant_client", client), patch.object(retrieval_service, "create_embedding", return_value=[.1]):
            retrieval_service.semantic_search("law", "owner", 5)
        conditions = client.query_points.call_args.kwargs["query_filter"].must
        self.assertTrue(any(getattr(condition.match, "any", None) == ["ready-doc"] for condition in conditions))
        self.assertTrue(any(getattr(condition.match, "value", None) == "owner" for condition in conditions))

    def test_cleanup_failure_keeps_failed_document_hidden_and_retryable(self):
        record = {"_id": ObjectId(), "status": "failed", "vector_cleanup_pending": True}
        collection = Mock()
        cleanup = Mock(side_effect=RuntimeError("private-url"))
        with self.assertLogs("app.services.document_lifecycle", "WARNING") as logs:
            document_lifecycle.cleanup_failed_document(collection, record, "owner", cleanup)
        collection.update_one.assert_not_called()
        self.assertNotIn("private-url", str(logs.output))
        cleanup.side_effect = None
        document_lifecycle.cleanup_failed_document(collection, record, "owner", cleanup)
        self.assertFalse(collection.update_one.call_args.args[1]["$set"]["vector_cleanup_pending"])

    def test_terminal_failure_deletes_partial_vectors_with_owner_scope(self):
        record = {"_id": ObjectId(), "filename": "law.pdf", "chunks": []}
        collection = Mock()
        collection.find_one_and_update.return_value = record
        collection.update_one.return_value = SimpleNamespace(matched_count=1)
        from app.services.vector_service import NonRetryableEmbeddingError
        with patch.object(document_tasks, "document_collection", collection), patch.object(document_tasks, "create_collection"), patch.object(document_tasks, "store_chunks", side_effect=NonRetryableEmbeddingError("quota")), patch.object(document_tasks, "delete_document_chunks") as cleanup:
            with self.assertRaises(NonRetryableEmbeddingError):
                document_tasks.index_document.run(str(record["_id"]), "owner")
        cleanup.assert_called_once_with(document_id=str(record["_id"]), user_id="owner")

    def test_stale_recovery_is_user_scoped_and_persists_sanitized_code(self):
        collection = Mock()
        document_lifecycle.recover_stale_documents(collection, "owner")
        query, update = collection.update_many.call_args.args
        self.assertEqual(query["user_id"], "owner")
        self.assertEqual(query["status"], "processing")
        self.assertIn("$lte", query["$or"][0]["processing_lease_expires_at"])
        self.assertEqual(update["$set"]["status"], "failed")
        self.assertEqual(update["$set"]["failure_code"], "processing_lease_expired")

    def test_failure_code_never_contains_exception_details(self):
        self.assertEqual(document_lifecycle.failure_code(RuntimeError("API_KEY=private")), "indexing_failed")
        self.assertEqual(document_lifecycle.failure_code(TimeoutError("private URL")), "indexing_timeout")

    def test_live_claim_is_fenced_and_lease_lost_stops_completion(self):
        collection = Mock()
        record = {"_id": ObjectId(), "filename": "law.pdf", "chunks": []}
        collection.find_one_and_update.return_value = record
        collection.update_one.return_value = SimpleNamespace(matched_count=0)
        def store(_chunks, progress_callback):
            progress_callback()
        with patch.object(document_tasks, "document_collection", collection), patch.object(document_tasks, "create_collection"), patch.object(document_tasks, "store_chunks", side_effect=store):
            result = document_tasks.index_document.run(str(record["_id"]), "owner")
        self.assertFalse(result["success"])
        claim = collection.find_one_and_update.call_args.args
        self.assertIn("processing_claim_id", claim[1]["$set"])
        self.assertGreater(claim[1]["$set"]["processing_lease_expires_at"], datetime.now(timezone.utc))
        self.assertEqual(collection.update_one.call_count, 1)

    def test_expired_claim_is_reclaimable_but_active_same_task_is_not(self):
        collection = Mock()
        collection.find_one_and_update.return_value = None
        with patch.object(document_tasks, "document_collection", collection):
            document_tasks.index_document.run(str(ObjectId()), "owner")
        clauses = collection.find_one_and_update.call_args.args[0]["$or"]
        self.assertTrue(any("processing_lease_expires_at" in clause for clause in clauses))
        same_task = [clause for clause in clauses if "indexing_task_id" in clause and isinstance(clause["indexing_task_id"], str)][0]
        self.assertEqual(same_task["processing_claim_id"], {"$exists": False})

    def test_completion_requires_live_lease_and_own_claim(self):
        record = {"_id": ObjectId(), "filename": "law.pdf", "chunks": []}
        collection = Mock()
        collection.find_one_and_update.return_value = record
        collection.update_one.return_value = SimpleNamespace(matched_count=0)
        with patch.object(document_tasks, "document_collection", collection), patch.object(document_tasks, "create_collection"), patch.object(document_tasks, "store_chunks", return_value=0):
            result = document_tasks.index_document.run(str(record["_id"]), "owner")
        self.assertFalse(result["success"])
        query = collection.update_one.call_args.args[0]
        self.assertIn("processing_claim_id", query)
        self.assertIn("$gt", query["processing_lease_expires_at"])
