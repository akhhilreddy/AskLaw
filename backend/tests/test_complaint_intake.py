"""Narrative intake tests are offline. No user descriptions reach a provider."""
import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api import complaint
from app.core.dependencies import get_current_user
from app.core import rate_limit
from app.schemas.complaint import ComplaintCase, IntakeRequest
from app.services import complaint_intake as service

DESCRIPTION = "Bought a laptop for INR 12k. Delivered broken on 2026-10-03. Seller refused refund. I want a refund."


def extraction(**changes):
    return service.Extraction.model_validate({"scope": "defective_product", "scope_excerpt": "Delivered broken",
        "facts": [{"field": "product", "excerpt": "laptop"}, {"field": "amount_inr", "excerpt": "INR 12k"},
                  {"field": "requested_resolution", "excerpt": "I want a refund."}],
        "events": [{"kind": "delivery", "excerpt": "Delivered broken on 2026-10-03.", "date_excerpt": "2026-10-03"}], **changes})


class NarrativeTests(unittest.TestCase):
    def test_grounded_candidates_never_become_evidence_or_confirmation(self):
        result = service.grounded_suggestions(DESCRIPTION, extraction())
        self.assertTrue(result["supported"])
        facts = {item["field"]: item["value"] for item in result["suggestions"] if "field" in item}
        self.assertEqual(facts["amount_inr"], "12000.00")
        self.assertNotIn("buyer_name", facts)
        events = [item["event"] for item in result["suggestions"] if "event" in item]
        data = ComplaintCase(title="Test", **facts, events=events)
        self.assertFalse(data.facts_confirmed)
        self.assertEqual(data.evidence, [])
        for item in result["suggestions"]:
            self.assertEqual(item["origin"], "user_report")
            self.assertIn(item["quote"], DESCRIPTION)
            self.assertNotIn("reference", item)

    def test_invented_values_dates_and_ambiguous_currency_are_dropped(self):
        result = service.grounded_suggestions(DESCRIPTION, extraction(
            facts=[{"field": "seller_name", "excerpt": "Made Up Seller"}, {"field": "amount_inr", "excerpt": "12k"}],
            events=[{"kind": "delivery", "excerpt": "Delivered broken", "date_excerpt": "2026-10-01"}]))
        self.assertEqual(len(result["suggestions"]), 3)
        self.assertIsNone(result["suggestions"][-1]["event"]["occurred_on"])
        self.assertEqual(result["suggestions"][-1]["event"]["evidence_ids"], [])
        for amount in ["USD 12k", "12k", "INR 1,,000", "INR 123,45", "INR -1", "INR NaN", "INR 99999999999"]:
            self.assertIsNone(service.amount_from_excerpt(amount), amount)
        for amount, value in [("INR 12k", "12000.00"), ("₹1.5 lakh", "150000.00"), ("Rs. 12,000", "12000.00"), ("12000 rupees", "12000.00")]:
            self.assertEqual(service.amount_from_excerpt(amount), value)

    def test_out_of_scope_and_false_classification_excerpt_have_no_suggestions(self):
        for parsed in [extraction(scope="out_of_scope"), extraction(scope_excerpt="invented")]:
            self.assertEqual(service.grounded_suggestions(DESCRIPTION, parsed), {"supported": False, "suggestions": []})

    def test_schema_forbids_extra_fields_and_unconsented_requests(self):
        for consent in [False, "true", 1, None]:
            with self.assertRaises(ValidationError):
                IntakeRequest(description=DESCRIPTION, consent_to_ai=consent)
        for text in ["short", "x" * 2001]:
            with self.assertRaises(ValidationError):
                IntakeRequest(description=text, consent_to_ai=True)
        with self.assertRaises(ValidationError):
            service.Extraction.model_validate({**extraction().model_dump(), "facts_confirmed": True})


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_success_uses_grounded_output_and_no_key_has_manual_fallback(self):
        with patch.object(service.settings, "GROQ_API_KEY", "test-only"), patch.object(service, "_extract", new=AsyncMock(return_value=extraction())) as provider:
            result = await service.prepare_intake(DESCRIPTION)
        self.assertTrue(result["supported"])
        provider.assert_awaited_once_with(DESCRIPTION)
        with patch.object(service.settings, "GROQ_API_KEY", ""), patch.object(service, "_extract", new=AsyncMock()) as provider:
            with self.assertRaises(HTTPException) as error:
                await service.prepare_intake(DESCRIPTION)
            self.assertEqual(error.exception.status_code, 503)
            self.assertIn("manual form", error.exception.detail)
            provider.assert_not_called()

    async def test_timeout_cancels_operation_and_errors_are_sanitized(self):
        cancelled = []
        async def slow(_description):
            try:
                await asyncio.sleep(10)
            finally:
                cancelled.append(True)
        real_wait_for = asyncio.wait_for
        async def bounded(operation, timeout):
            self.assertEqual(timeout, 25)
            return await real_wait_for(operation, timeout=0.001)
        with patch.object(service.settings, "GROQ_API_KEY", "test"), patch.object(service, "_extract", side_effect=slow), patch.object(service.asyncio, "wait_for", side_effect=bounded), self.assertLogs(service.logger, "WARNING"):
            with self.assertRaises(HTTPException):
                await service.prepare_intake(DESCRIPTION)
        self.assertEqual(cancelled, [True])
        with patch.object(service.settings, "GROQ_API_KEY", "test"), patch.object(service, "_extract", new=AsyncMock(side_effect=ValueError("secret https://provider.invalid/?private=data"))), self.assertLogs(service.logger, "WARNING") as logs:
            with self.assertRaises(HTTPException) as error:
                await service.prepare_intake(DESCRIPTION)
        self.assertNotIn("private", str(logs.output) + error.exception.detail)

    async def test_sdk_has_explicit_timeout_zero_retries_and_bounded_json(self):
        client = MagicMock()
        client.chat.completions.create = AsyncMock(return_value=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=extraction().model_dump_json()))]))
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=client)
        context.__aexit__ = AsyncMock(return_value=False)
        with patch.object(service, "AsyncGroq", return_value=context) as sdk:
            await service._extract(DESCRIPTION)
        self.assertEqual(sdk.call_args.kwargs["max_retries"], 0)
        self.assertEqual(sdk.call_args.kwargs["timeout"].connect, 5)
        self.assertEqual(sdk.call_args.kwargs["timeout"].read, 20)
        self.assertEqual(client.chat.completions.create.call_args.kwargs["response_format"], {"type": "json_object"})
        client.chat.completions.create.return_value.choices[0].message.content = "Not JSON"
        with patch.object(service, "AsyncGroq", return_value=context), self.assertRaises(ValidationError):
            await service._extract(DESCRIPTION)


class IntakeAPITests(unittest.TestCase):
    def test_auth_guests_limits_consent_and_no_save(self):
        app = FastAPI()
        app.include_router(complaint.router, prefix="/complaints")
        body = {"description": DESCRIPTION, "consent_to_ai": True}
        with TestClient(app) as client, patch.object(rate_limit, "admit", return_value=None), patch.object(rate_limit, "release"), patch.object(complaint, "prepare_intake", new=AsyncMock(return_value={"supported": True, "suggestions": []})) as provider, patch.object(complaint.service, "save_case") as save:
            self.assertEqual(client.post("/complaints/intake", json=body).status_code, 401)
            app.dependency_overrides[get_current_user] = lambda: {"_id": "guest", "is_guest": True}
            self.assertEqual(client.post("/complaints/intake", json=body).status_code, 403)
            app.dependency_overrides[get_current_user] = lambda: {"_id": "owner"}
            self.assertEqual(client.post("/complaints/intake", json={**body, "consent_to_ai": False}).status_code, 422)
            provider.assert_not_called()
            self.assertEqual(client.post("/complaints/intake", json=body).status_code, 200)
            provider.assert_awaited_once_with(DESCRIPTION)
            save.assert_not_called()
            with patch.object(rate_limit, "admit", side_effect=HTTPException(429, "Please wait", headers={"Retry-After": "60"})):
                response = client.post("/complaints/intake", json=body)
            self.assertEqual(response.status_code, 429)
            self.assertEqual(response.headers["retry-after"], "60")
