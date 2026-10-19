"""Offline complaint schema, ownership, revision, source and preparation checks."""
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from bson import ObjectId
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pymongo.errors import ServerSelectionTimeoutError

from app.api import complaint
from app.core import rate_limit
from app.core.dependencies import get_current_user
from app.schemas.agreement import AgreementText
from app.schemas.complaint import ComplaintCase, EvidenceReference
from app.services import complaint_service as service


def facts(**updates):
    return ComplaintCase.model_validate({"title": "Fictional laptop refund", "buyer_name": "Sample Buyer",
        "seller_name": "Sample Seller", "seller_contact": "Seller contact supplied by user", "product": "Fictional laptop",
        "description": "I report damage on delivery.", "requested_resolution": "I request a refund.",
        "amount_inr": "12000.00", "facts_confirmed": True, **updates})


class Cursor(list):
    def sort(self, _order):
        return self

    def limit(self, count):
        return self[:count]


class Collection:
    def __init__(self):
        self.records = {}
        self.filters = []

    def matches(self, item, query):
        return all(item.get(key) == value for key, value in query.items())

    def find_one(self, query):
        self.filters.append(query)
        return next((deepcopy(item) for item in self.records.values() if self.matches(item, query)), None)

    def find(self, query, projection):
        self.filters.append(query)
        return Cursor(deepcopy(item) for item in self.records.values() if self.matches(item, query))

    def insert_one(self, record):
        identifier = ObjectId()
        self.records[identifier] = {**deepcopy(record), "_id": identifier}
        return SimpleNamespace(inserted_id=identifier)

    def update_one(self, query, update):
        self.filters.append(query)
        for item in self.records.values():
            if self.matches(item, query):
                item.update(deepcopy(update["$set"]))
                item["revision"] += update["$inc"]["revision"]
                return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)

    def delete_one(self, query):
        self.filters.append(query)
        for identifier, item in list(self.records.items()):
            if self.matches(item, query):
                del self.records[identifier]
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)


class ComplaintSchemaTests(unittest.TestCase):
    def test_rejects_unbounded_fields_invalid_amounts_and_foreign_model_fields(self):
        for updates in [{"title": " "}, {"buyer_name": "x" * 201}, {"amount_inr": "-1"}, {"amount_inr": "NaN"},
                        {"amount_inr": "1,000"}, {"amount_inr": "1.234"}, {"user_id": "attacker"},
                        {"facts_confirmed": "true"}, {"letter_text": "a" * 16001}]:
            with self.subTest(updates=updates), self.assertRaises(ValidationError):
                facts(**updates)

    def test_dates_unknown_links_and_duplicate_ids_are_checked(self):
        base = {"event_id": "t1", "kind": "purchase", "description": "User-reported purchase", "occurred_on": "2026-02-30"}
        with self.assertRaises(ValidationError):
            facts(events=[base])
        for events in [[{**base, "occurred_on": None, "evidence_ids": ["missing"]}],
                       [{**base, "occurred_on": None}] * 2]:
            with self.assertRaises(ValidationError):
                facts(events=events)
        self.assertIsNone(facts(events=[{**base, "occurred_on": None}]).events[0].occurred_on)

    def test_quote_bounds_and_evidence_count_are_capped(self):
        reference = {"evidence_id": "e1", "document_id": str(ObjectId()), "label": "Invoice", "page_number": 1, "start": 0, "end": 1, "page_text_sha256": "0" * 64}
        for changes in [{"start": True}, {"end": 0}, {"end": 2001}, {"page_number": 51}, {"quote": "forged"}]:
            with self.assertRaises(ValidationError):
                EvidenceReference.model_validate({**reference, **changes})
        with self.assertRaises(ValidationError):
            facts(evidence=[reference] * 16)


class ComplaintPackTests(unittest.TestCase):
    def test_letter_is_compact_and_attributes_seller_voice_without_dropping_source_text(self):
        long_reply = "We decline the refund and offer inspection. " * 12
        refs = [{"evidence_id": "e1", "label": "Seller reply", "category": "correspondence", "available": True, "quote": long_reply}]
        data = facts(events=[{"event_id": "a", "kind": "response", "description": "We decline your refund.", "evidence_ids": ["e1"]},
            {"event_id": "b", "kind": "response", "description": long_reply, "evidence_ids": ["e1"]},
            {"event_id": "c", "kind": "contact", "description": "Repeated long correspondence. " * 20}],
            evidence=[{"evidence_id": "e1", "document_id": str(ObjectId()), "label": "Reply", "page_number": 1, "start": 0, "end": 1, "page_text_sha256": "0" * 64}])
        pack = service.build_pack(data, refs)
        self.assertIn('Seller response (as recorded): "We decline your refund."', pack["draft_letter"])
        self.assertIn("Linked excerpts: E1", pack["draft_letter"])
        self.assertNotIn(long_reply, pack["draft_letter"])
        self.assertEqual(pack["timeline"][1]["description"], long_reply.strip())
        self.assertEqual(pack["evidence"][0]["quote"], long_reply)

    def test_unavailable_sources_are_not_cited_by_the_draft(self):
        data = facts(events=[{"event_id": "r", "kind": "response", "description": "We offer repair.", "evidence_ids": ["e1"]}],
            evidence=[{"evidence_id": "e1", "document_id": str(ObjectId()), "label": "Reply", "page_number": 1, "start": 0, "end": 1, "page_text_sha256": "0" * 64}])
        pack = service.build_pack(data, [{"evidence_id": "e1", "category": "correspondence", "available": False}])
        self.assertNotIn("Linked excerpts", pack["draft_letter"])
        self.assertIn('Seller response (as recorded): "We offer repair."', pack["draft_letter"])

    def test_missing_confirmation_or_required_fields_prevents_letter_but_keeps_checklist(self):
        for data in [facts(facts_confirmed=False), facts(seller_name=""), facts(description="")]:
            pack = service.build_pack(data, [])
            self.assertFalse(pack["draft_ready"])
            self.assertIsNone(pack["draft_letter"])
            self.assertTrue(any(not item["complete"] for item in pack["checklist"]))

    def test_timeline_orders_known_dates_and_labels_unknown_dates_without_inventing_them(self):
        data = facts(events=[{"event_id": "a", "kind": "response", "description": "Reply date unknown"},
            {"event_id": "b", "kind": "contact", "description": "Contacted seller", "occurred_on": "2026-10-08"},
            {"event_id": "c", "kind": "purchase", "description": "Purchased", "occurred_on": "2026-10-01"}])
        pack = service.build_pack(data, [])
        self.assertEqual([event["event_id"] for event in pack["timeline"]], ["c", "b", "a"])
        self.assertIn("Date not supplied", pack["draft_letter"])
        self.assertIn("INR 12000.00", pack["draft_letter"])
        self.assertNotIn("Consumer Protection Act", pack["draft_letter"])
        self.assertNotIn("guaranteed", pack["draft_letter"])
        self.assertIn("not legal advice", pack["disclaimer"])

    def test_deleted_evidence_is_not_counted_as_recorded_and_user_edited_letter_remains_user_text(self):
        pack = service.build_pack(facts(letter_text="My reviewed custom letter."), [
            {"evidence_id": "e1", "label": "Missing invoice", "category": "invoice", "available": False}])
        invoice = next(item for item in pack["checklist"] if item["key"] == "invoice")
        self.assertFalse(invoice["complete"])
        self.assertTrue(pack["user_edited_draft"])
        self.assertEqual(pack["draft_letter"], "My reviewed custom letter.")


class ComplaintApiTests(unittest.TestCase):
    def setUp(self):
        self.collection = Collection()
        self.owner = str(ObjectId())
        self.document_id = str(ObjectId())
        self.source = AgreementText(document_id=self.document_id, title="synthetic-invoice.pdf", page_count=1,
            pages=[{"page_number": 1, "text": "Synthetic invoice 🏠\nAmount: INR 12000.00.\nNot proof of an actual purchase."}])
        self.reference = {"evidence_id": "e1", "document_id": self.document_id, "label": "Invoice amount", "category": "invoice", "page_number": 1,
                          "start": self.source.pages[0].text.index("Amount"), "end": self.source.pages[0].text.index("\nNot"),
                          "page_text_sha256": sha256(self.source.pages[0].text.encode()).hexdigest()}
        self.app = FastAPI()
        self.app.include_router(complaint.router, prefix="/complaints")
        self.app.dependency_overrides[get_current_user] = lambda: {"_id": self.owner}
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.patches = [patch.object(service, "complaint_collection", self.collection),
            patch.object(service, "load_agreement_document", return_value=self.source),
            patch.object(rate_limit, "admit", return_value=None), patch.object(rate_limit, "release")]
        self.mocks = [item.start() for item in self.patches]
        self.addCleanup(lambda: [item.stop() for item in reversed(self.patches)])

    def create(self, data=None):
        response = self.client.post("/complaints", json=(data or facts()).model_dump())
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_create_list_resume_update_pack_and_delete(self):
        saved = self.create(facts(evidence=[self.reference]))
        case_id = saved["case_id"]
        self.assertEqual(self.client.get("/complaints").json()[0]["case_id"], case_id)
        self.assertEqual(self.client.get(f"/complaints/{case_id}").json()["data"]["title"], facts().title)
        changed = self.client.put(f"/complaints/{case_id}", json={"revision": 1, "data": facts(title="Changed", evidence=[self.reference]).model_dump()})
        self.assertEqual(changed.json()["revision"], 2)
        response = self.client.post(f"/complaints/{case_id}/pack", json={"revision": 2})
        self.assertEqual(response.status_code, 200, response.text)
        item = response.json()["evidence"][0]
        self.assertEqual(item["quote"], self.source.pages[0].text[self.reference["start"]:self.reference["end"]])
        self.assertEqual(item["page_text_sha256"], sha256(self.source.pages[0].text.encode()).hexdigest())
        stored = self.collection.records[ObjectId(case_id)]
        self.assertNotIn("quote", stored["data"]["evidence"][0])
        self.assertEqual(stored["data"]["evidence"][0]["page_text_sha256"], self.reference["page_text_sha256"])
        self.assertEqual(self.client.delete(f"/complaints/{case_id}?revision=2").status_code, 200)
        self.assertEqual(self.client.get(f"/complaints/{case_id}").status_code, 404)
        self.assertTrue(all(query.get("user_id") == self.owner for query in self.collection.filters))

    def test_other_user_cannot_read_update_export_or_delete(self):
        saved = self.create()
        self.app.dependency_overrides[get_current_user] = lambda: {"_id": "someone-else"}
        case_id = saved["case_id"]
        self.assertEqual(self.client.get("/complaints").json(), [])
        for method, url, body in [("get", f"/complaints/{case_id}", None),
                ("put", f"/complaints/{case_id}", {"revision": 1, "data": facts().model_dump()}),
                ("post", f"/complaints/{case_id}/pack", {"revision": 1}),
                ("delete", f"/complaints/{case_id}?revision=1", None)]:
            response = getattr(self.client, method)(url, **({"json": body} if body else {}))
            self.assertEqual(response.status_code, 404)

    def test_unowned_source_is_refused_and_page_endpoint_checks_owner(self):
        self.mocks[1].side_effect = HTTPException(404, "Document not found")
        response = self.client.post("/complaints", json=facts(evidence=[self.reference]).model_dump())
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.collection.records, {})
        self.mocks[1].assert_called_with(self.document_id, self.owner)
        with patch.object(complaint, "load_agreement_document", side_effect=HTTPException(404, "Document not found")) as loader:
            self.assertEqual(self.client.get(f"/complaints/documents/{self.document_id}/pages/1").status_code, 404)
            loader.assert_called_once_with(self.document_id, self.owner)

    def test_deleted_pdf_drops_quote_on_later_pack_and_invalid_ranges_cannot_be_saved(self):
        saved = self.create(facts(evidence=[self.reference]))
        self.mocks[1].side_effect = HTTPException(404, "Document not found")
        pack = self.client.post(f"/complaints/{saved['case_id']}/pack", json={"revision": 1})
        self.assertEqual(pack.status_code, 200)
        self.assertFalse(pack.json()["evidence"][0]["available"])
        self.assertNotIn("quote", pack.json()["evidence"][0])
        self.mocks[1].side_effect = None
        for changes in [{"page_number": 2}, {"end": 1000}]:
            response = self.client.post("/complaints", json=facts(evidence=[{**self.reference, **changes}]).model_dump())
            self.assertEqual(response.status_code, 422)

    def test_stale_revisions_do_not_overwrite_delete_or_generate_current_pack(self):
        saved = self.create()
        case_id = saved["case_id"]
        self.client.put(f"/complaints/{case_id}", json={"revision": 1, "data": facts(title="Latest").model_dump()})
        self.assertEqual(self.client.put(f"/complaints/{case_id}", json={"revision": 1, "data": facts().model_dump()}).status_code, 409)
        self.assertEqual(self.client.delete(f"/complaints/{case_id}?revision=1").status_code, 409)
        self.assertEqual(self.client.post(f"/complaints/{case_id}/pack", json={"revision": 1}).status_code, 409)
        self.assertEqual(self.client.get(f"/complaints/{case_id}").json()["data"]["title"], "Latest")

    def test_guest_and_unauthenticated_requests_cannot_access_private_workspaces(self):
        self.app.dependency_overrides.clear()
        self.assertEqual(self.client.get("/complaints").status_code, 401)
        self.app.dependency_overrides[get_current_user] = lambda: {"_id": "guest", "is_guest": True}
        self.assertEqual(self.client.get("/complaints").status_code, 403)
        self.assertEqual(self.client.post("/complaints", json=facts().model_dump()).status_code, 403)

    def test_rate_limit_errors_preserve_retry_after_and_database_errors_are_sanitized(self):
        self.mocks[2].side_effect = HTTPException(429, "Please wait", headers={"Retry-After": "60"})
        response = self.client.post("/complaints", json=facts().model_dump())
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["retry-after"], "60")
        self.mocks[2].side_effect = None
        with patch.object(self.collection, "find", side_effect=ServerSelectionTimeoutError("secret provider URL")), self.assertLogs(service.logger, "WARNING") as logs, patch.object(service, "timeout") as budget:
            response = self.client.get("/complaints")
        budget.assert_called_once_with(5)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("secret", response.text + str(logs.output))

    def test_source_failure_does_not_misrepresent_outage_as_deleted_evidence(self):
        saved = self.create(facts(evidence=[self.reference]))
        self.mocks[1].side_effect = HTTPException(503, "Document library temporarily unavailable")
        response = self.client.post(f"/complaints/{saved['case_id']}/pack", json={"revision": 1})
        self.assertEqual(response.status_code, 503)

    def test_changed_or_forged_page_hash_does_not_silently_rebind_evidence(self):
        saved = self.create(facts(evidence=[self.reference]))
        forged = {**self.reference, "page_text_sha256": "0" * 64}
        self.assertEqual(self.client.post("/complaints", json=facts(evidence=[forged]).model_dump()).status_code, 422)
        changed = self.source.model_copy(update={"pages": [self.source.pages[0].model_copy(update={"text": "Edited page content"})]})
        self.mocks[1].return_value = changed
        response = self.client.post(f"/complaints/{saved['case_id']}/pack", json={"revision": 1})
        self.assertFalse(response.json()["evidence"][0]["available"])
        self.assertNotIn("quote", response.json()["evidence"][0])

    def test_source_page_returns_only_owned_page_and_server_hash(self):
        with patch.object(complaint, "load_agreement_document", return_value=self.source) as loader:
            response = self.client.get(f"/complaints/documents/{self.document_id}/pages/1")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["page_text_sha256"], self.reference["page_text_sha256"])
            loader.assert_called_once_with(self.document_id, self.owner)
            self.assertEqual(self.client.get(f"/complaints/documents/{self.document_id}/pages/2").status_code, 404)


if __name__ == "__main__":
    unittest.main()
