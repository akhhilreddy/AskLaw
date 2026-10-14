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
from app.services import document_lifecycle
from app.tasks import document_tasks


class DocumentLeaseTests(unittest.TestCase):
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
