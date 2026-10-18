"""Offline API, isolation and upload-adapter regression tests."""
import io
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from bson import ObjectId
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pymongo.errors import ServerSelectionTimeoutError
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.api import agreement
from app.core import rate_limit
from app.core.dependencies import get_current_user
from app.services import agreement_documents, document_service


class AgreementApiTests(unittest.TestCase):
    def setUp(self):
        self.owner = str(ObjectId())
        self.original, self.revised, self.foreign = [str(ObjectId()) for _ in range(3)]
        self.records = {}
        for doc_id, text in [(self.original, "Security deposit: INR 10,000.\n\nGive 30 days notice."),
                             (self.revised, "Security deposit: INR 15,000.\n\nGive 90 days notice.")]:
            self.records[doc_id] = {"_id": ObjectId(doc_id), "user_id": self.owner,
                "filename": "rental.pdf", "status": "indexed", "page_count": 1,
                **agreement_documents.capture_pages("rental.pdf", 1, [{"page_number": 1, "text": text}])}
        self.collection = Mock()
        self.collection.find_one.side_effect = lambda query, projection: self.records.get(str(query["_id"])) if query.get("user_id") == self.owner else None
        self.app = FastAPI()
        self.app.include_router(agreement.router, prefix="/agreements")
        self.app.dependency_overrides[get_current_user] = lambda: {"_id": self.owner}
        self.client = TestClient(self.app)
        self.patches = [patch.object(agreement_documents, "document_collection", self.collection),
                        patch.object(rate_limit, "admit", return_value=None), patch.object(rate_limit, "release")]
        self.mocks = [item.start() for item in self.patches]
        self.addCleanup(lambda: [item.stop() for item in reversed(self.patches)])
        self.addCleanup(self.client.close)

    def test_review_and_compare_quote_owned_pages_and_use_shared_limits(self):
        review = self.client.post("/agreements/review", json={"document_id": self.original})
        self.assertEqual(review.status_code, 200)
        self.assertEqual(review.json()["terms"][0]["mentions"][0]["page_number"], 1)
        comparison = self.client.post("/agreements/compare", json={"before_id": self.original, "after_id": self.revised})
        self.assertEqual(comparison.status_code, 200)
        self.assertIn("INR 15,000", str(comparison.json()["changes"]))
        for call in self.collection.find_one.call_args_list:
            self.assertEqual(call.args[0]["user_id"], self.owner)
        self.assertEqual(self.mocks[1].call_count, 2)
        self.assertEqual(self.mocks[2].call_count, 2)
        self.assertEqual(self.mocks[1].call_args.kwargs["concurrency"], 2)

    def test_either_unowned_comparison_side_is_hidden(self):
        for first, second in [(self.foreign, self.revised), (self.original, self.foreign)]:
            response = self.client.post("/agreements/compare", json={"before_id": first, "after_id": second})
            self.assertEqual(response.status_code, 404)
            self.assertNotIn("deposit", response.text)
        self.app.dependency_overrides[get_current_user] = lambda: {"_id": "another-user"}
        response = self.client.post("/agreements/review", json={"document_id": self.original})
        self.assertEqual(response.status_code, 404)

    def test_unauthenticated_and_guest_access(self):
        self.app.dependency_overrides.clear()
        self.assertEqual(self.client.get("/agreements/documents").status_code, 401)
        self.app.dependency_overrides[get_current_user] = lambda: {"_id": "guest", "is_guest": True}
        self.assertEqual(self.client.get("/agreements/documents").status_code, 403)
        self.assertEqual(self.client.post("/agreements/review", json={"document_id": self.original}).status_code, 403)
        self.collection.reset_mock()
        demo = self.client.get("/agreements/demo")
        self.assertEqual(demo.status_code, 200)
        self.assertTrue(demo.json()["sample"])
        self.assertIn("Sample rental agreement", demo.json()["review"]["title"])
        self.collection.find_one.assert_not_called()
        self.collection.find.assert_not_called()

    def test_old_failed_partial_and_corrupt_documents_fail_honestly(self):
        original = self.records[self.original]
        for edits in [{"agreement_text_version": None}, {"status": "processing"}, {"status": "failed"},
                      {"agreement_review_available": False}, {"page_count": 2},
                      {"agreement_pages": [{"page_number": 1, "text": "bad\ufffdtext"}]}]:
            self.records[self.original] = {**original, **edits}
            response = self.client.post("/agreements/review", json={"document_id": self.original})
            self.assertEqual(response.status_code, 409, response.text)
            self.assertNotIn("bad\ufffdtext", response.text)

    def test_db_outage_is_sanitized_with_bounded_wait(self):
        self.collection.find_one.side_effect = ServerSelectionTimeoutError("secret DB URL")
        with patch.object(agreement_documents, "timeout") as deadline, self.assertLogs(agreement_documents.logger, "WARNING") as logs:
            response = self.client.post("/agreements/review", json={"document_id": self.original})
        self.assertEqual(response.status_code, 503)
        deadline.assert_called_once_with(5)
        self.assertNotIn("secret", response.text + str(logs.output))

    def test_strict_ids_same_version_and_extra_text_are_rejected(self):
        for payload in [{"before_id": self.original, "after_id": self.original},
                        {"before_id": "bad", "after_id": self.revised},
                        {"before_id": self.original, "after_id": self.revised, "user_id": self.owner}]:
            self.assertEqual(self.client.post("/agreements/compare", json=payload).status_code, 422)
        self.collection.find_one.assert_not_called()

    def test_rate_limit_retry_header_and_release_on_analysis_failure(self):
        self.mocks[1].side_effect = HTTPException(429, "Please wait.", headers={"Retry-After": "60"})
        response = self.client.get("/agreements/demo")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["retry-after"], "60")
        self.mocks[1].side_effect = None
        with patch.object(agreement, "review_agreement", side_effect=ValueError("private document text")):
            response = self.client.post("/agreements/review", json={"document_id": self.original})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn("private", response.text)
        self.mocks[2].assert_called()

    def test_listing_is_owner_scoped_bounded_and_omits_text(self):
        class Cursor(list):
            def sort(inner, _order):
                return inner

            def limit(inner, count):
                self.assertEqual(count, 100)
                return inner
        self.collection.find.return_value = Cursor(self.records.values())
        result = self.client.get("/agreements/documents")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.collection.find.call_args.args[0], {"user_id": self.owner})
        self.assertNotIn("agreement_pages", self.collection.find.call_args.args[1])
        self.assertNotIn("deposit", result.text)


class AgreementUploadTests(unittest.TestCase):
    def test_real_pdf_extraction_to_owned_api_comparison_preserves_page_two(self):
        def pdf(deposit, notice):
            writer = PdfWriter()
            for lines in [["SYNTHETIC TEST ONLY", "Monthly rent INR 12,000."],
                          [f"Security deposit INR {deposit}.", f"Give {notice} days notice."]]:
                page = writer.add_blank_page(width=595, height=842)
                font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                    NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
                page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
                stream = DecodedStreamObject()
                stream.set_data(("BT /F1 12 Tf 50 750 Td " + " 0 -48 Td ".join(f"({line}) Tj" for line in lines) + " ET").encode("ascii"))
                page[NameObject("/Contents")] = writer._add_object(stream)
            output = io.BytesIO()
            writer.write(output)
            output.seek(0)
            return output

        records = {}
        collection = Mock()

        def insert(record):
            identifier = ObjectId()
            records[str(identifier)] = {**record, "_id": identifier, "status": "indexed"}
            return SimpleNamespace(inserted_id=identifier)

        collection.insert_one.side_effect = insert
        collection.find_one.side_effect = lambda query, projection: records.get(str(query["_id"])) if query.get("user_id") == "owner" else None
        ids = []
        with patch.object(document_service, "document_collection", collection), patch.object(document_service.index_document, "delay", return_value=SimpleNamespace(id="task")):
            for deposit, notice in [("10,000", 30), ("15,000", 90)]:
                upload = SimpleNamespace(filename="synthetic-rental.pdf", content_type="application/pdf", file=pdf(deposit, notice))
                ids.append(document_service.save_uploaded_document(upload, "owner")["document_id"])
        app = FastAPI()
        app.include_router(agreement.router, prefix="/agreements")
        app.dependency_overrides[get_current_user] = lambda: {"_id": "owner"}
        with patch.object(agreement_documents, "document_collection", collection), patch.object(rate_limit, "admit", return_value=None), patch.object(rate_limit, "release"), TestClient(app) as client:
            response = client.post("/agreements/compare", json={"before_id": ids[0], "after_id": ids[1]})
        self.assertEqual(response.status_code, 200)
        changes = response.json()["changes"]
        self.assertTrue(changes)
        for change in changes:
            for side in ["before", "after"]:
                for passage in change[side]:
                    self.assertEqual(passage["page_number"], 2)
                    stored_page = records[passage["document_id"]]["agreement_pages"][1]["text"]
                    self.assertEqual(passage["quote"], stored_page[passage["start"]:passage["end"]])
        self.assertIn("90 days", str(changes))
        self.assertIn("INR 15,000", str(changes))

    def test_page_capture_does_not_change_existing_chunks_or_queue_flow(self):
        for texts, supported in [(["Rent: INR 12,000.", "Give 30 days notice."], True),
                                 (["Rent: INR 12,000.", None], False),
                                 (["Rent: INR 12,000.", "bad\ufffdtext"], False)]:
            with self.subTest(texts=texts):
                collection = Mock()
                collection.insert_one.return_value = SimpleNamespace(inserted_id=ObjectId())
                pages = [SimpleNamespace(extract_text=Mock(return_value=text)) for text in texts]
                upload = SimpleNamespace(filename="rental.pdf", content_type="application/pdf", size=8, file=io.BytesIO(b"%PDF-1.7"))
                with patch.object(document_service, "PdfReader", return_value=SimpleNamespace(pages=pages)), patch.object(document_service, "document_collection", collection), patch.object(document_service.index_document, "delay", return_value=SimpleNamespace(id="task")) as enqueue:
                    result = document_service.save_uploaded_document(upload, "owner")
                record = collection.insert_one.call_args.args[0]
                self.assertEqual(record["agreement_review_available"], supported)
                self.assertEqual(record["status"], "uploaded")
                self.assertEqual(record["page_count"], 2)
                self.assertEqual(record["content"], "\n\n".join(text for text in texts if text))
                self.assertEqual(record["chunks"], [{"index": index, "page_number": index + 1, "text": text} for index, text in enumerate(texts) if text])
                self.assertEqual(result["task_id"], "task")
                enqueue.assert_called_once_with(result["document_id"], "owner")
                if supported:
                    self.assertEqual([page["text"] for page in record["agreement_pages"]], texts)
                else:
                    self.assertNotIn("agreement_pages", record)

    def test_capture_is_bounded_and_requires_complete_ordered_pages(self):
        for pages, count in [([{ "page_number": 2, "text": "Rent"}], 2),
                             ([{"page_number": 1, "text": "a" * 100001}], 1),
                             ([{"page_number": 1, "text": "Rent"}], 51)]:
            result = agreement_documents.capture_pages("rental.pdf", count, pages)
            self.assertFalse(result["agreement_review_available"])
            self.assertNotIn("agreement_pages", result)
