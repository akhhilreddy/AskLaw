import asyncio
import base64
import json
import logging
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "7")
from bson import ObjectId
import httpx
from app.services import availability as availability, conversation_service, ai_service
from app.services import retrieval_orchestrator as orchestrator, research_runtime
from app.schemas.chat import ChatMessage
from app.schemas.conversation import ConversationMessageCreate
from app.services.query_router import QueryRoute


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.items = [{"type": "web_unavailable"}]
        self.receipt = availability.sign_availability("owner", "conversation", "answer", self.items, now=1000)

    def test_valid_receipt_is_non_jwt_and_bound_metadata(self):
        self.assertEqual(len(self.receipt.split(".")), 2)
        result = availability.verify_availability(self.receipt, "owner", "conversation", "answer", now=1001)
        self.assertEqual(result["availability_notices"], self.items)
        self.assertFalse(result["availability_only"])
        raw = base64.urlsafe_b64decode(self.receipt.split(".")[0] + "==")
        self.assertNotIn(b"answer\"", raw)
        self.assertNotIn(b"http", raw)

    def test_tampered_text_wrong_user_wrong_conversation_expired_reused_and_malformed(self):
        cases = [
            (self.receipt, "owner", "conversation", "tampered text", 1001),
            (self.receipt, "wrong-user", "conversation", "answer", 1001),
            (self.receipt, "owner", "wrong-conversation", "answer", 1001),
            (self.receipt, "owner", "conversation", "answer", 1301),
            (self.receipt, "owner", "conversation", "different answer", 1001),
            ("malformed.private-provider-url", "owner", "conversation", "answer", 1001),
            (self.receipt[:-1] + "!", "owner", "conversation", "answer", 1001),
            ("x" * 5000, "owner", "conversation", "answer", 1001),
        ]
        for receipt, user, conversation, text, now in cases:
            with self.subTest(user=user, conversation=conversation, now=now), self.assertLogs(availability.logger, "WARNING") as logs:
                self.assertEqual(availability.verify_availability(receipt, user, conversation, text, now=now), {})
                self.assertNotIn("private-provider-url", str(logs.output))

    def test_missing_receipt_is_normal_message_and_notice_allowlist_is_strict(self):
        self.assertEqual(availability.verify_availability(None, "owner", "conversation", "answer"), {})
        for items in [[{"type": "https://secret-provider?q=private"}], [{"type": "web_unavailable", "url": "private"}]]:
            with self.assertRaises(ValueError):
                availability.sign_availability("owner", "conversation", "answer", items)

    def test_derived_key_and_constant_time_comparison(self):
        self.assertNotEqual(availability._key(), availability.settings.SECRET_KEY.encode())
        with patch.object(availability.hmac, "compare_digest", wraps=availability.hmac.compare_digest) as compare:
            availability.verify_availability(self.receipt, "owner", "conversation", "answer", now=1001)
        self.assertEqual(compare.call_count, 2)

    def test_invalid_receipt_saves_normally_without_notices(self):
        collection = Mock()
        collection.update_one.return_value = SimpleNamespace(matched_count=1)
        with patch.object(conversation_service, "conversation_collection", collection), self.assertLogs(availability.logger, "WARNING"):
            result = conversation_service.add_message(str(ObjectId()), "owner", "assistant", "answer", "invalid")
        self.assertEqual(result["content"], "answer")
        self.assertNotIn("availability_notices", result)
        self.assertNotIn("availability_notices", collection.update_one.call_args.args[1]["$push"]["messages"])
        self.assertIsNone(ConversationMessageCreate(role="assistant", content="answer", availability_receipt="x" * 5000).availability_receipt)
        self.assertIsNone(ConversationMessageCreate(role="assistant", content="answer", availability_receipt={"forged": True}).availability_receipt)

    def test_valid_receipt_round_trips_as_structured_notices(self):
        identifier = str(ObjectId())
        receipt = availability.sign_availability("owner", identifier, "answer", self.items, availability_only=True)
        collection = Mock()
        collection.update_one.return_value = SimpleNamespace(matched_count=1)
        with patch.object(conversation_service, "conversation_collection", collection):
            result = conversation_service.add_message(identifier, "owner", "assistant", "answer", receipt)
            saved = collection.update_one.call_args.args[1]["$push"]["messages"]
            collection.find_one.return_value = {"_id": ObjectId(identifier), "messages": [saved]}
            loaded = conversation_service.get_conversation(identifier, "owner")
        self.assertEqual(result["availability_notices"], self.items)
        self.assertTrue(loaded["messages"][0]["availability_only"])
        self.assertEqual(loaded["messages"][0]["availability_notices"], self.items)


class DependencyTests(unittest.TestCase):
    def test_receipt_conversation_binding_requires_owning_user_in_chat_endpoint(self):
        from app.api import chat
        from app.schemas.chat import ChatRequest
        from fastapi import HTTPException
        identifier = str(ObjectId())
        request = ChatRequest(messages=[{"role": "user", "content": "research"}], conversation_id=identifier)
        with patch.object(chat, "get_conversation", return_value=None) as owned, patch.object(chat, "stream_response") as stream:
            with self.assertRaises(HTTPException) as failure:
                chat.chat_stream(request, {"_id": "owner"})
        self.assertEqual(failure.exception.status_code, 404)
        owned.assert_called_once_with(identifier, "owner")
        stream.assert_not_called()

    def test_outage_and_empty_results_are_distinct_and_content_cannot_forge_status(self):
        with patch.object(orchestrator, "ensure_web_ready", new=AsyncMock(return_value=True)):
            for response, expected in [
                (availability.SearchResponse({"results": []}, unavailable=True), [{"type": "web_unavailable"}]),
                ({"results": []}, []),
                ({"results": [], "error": "outage", "availability_notices": [{"type": "web_unavailable"}]}, []),
            ]:
                with patch.object(orchestrator, "search_web", new=AsyncMock(return_value=response)):
                    result = asyncio.run(orchestrator.retrieve_for_query("what is law?", "owner"))
                self.assertEqual(result.get("availability_notices", []), expected)

    def test_hybrid_retains_evidence_when_either_dependency_fails(self):
        evidence = [{"text": "evidence"}]
        for rag_error, web_error, expected in [(True, False, "rag_unavailable"), (False, True, "web_unavailable")]:
            with patch.object(orchestrator, "route_query", return_value=QueryRoute.HYBRID), patch.object(orchestrator, "retrieve_rag", side_effect=RuntimeError("private-url?query") if rag_error else None, return_value=evidence), patch.object(orchestrator, "retrieve_web", new=AsyncMock(side_effect=RuntimeError("private-url?query") if web_error else None, return_value=evidence)):
                result = asyncio.run(orchestrator.retrieve_for_query("research", "owner", "owned-document"))
            self.assertEqual(result["web_results"] if rag_error else result["rag_results"], evidence)
            self.assertEqual(result["availability_notices"], [{"type": expected}])

    def test_hybrid_deadline_keeps_already_completed_rag(self):
        async def slow(*_args):
            await asyncio.sleep(1)
        with patch.object(orchestrator.settings, "RESEARCH_DEADLINE_SECONDS", .06), patch.object(orchestrator, "route_query", return_value=QueryRoute.HYBRID), patch.object(orchestrator, "retrieve_rag", return_value=[{"text": "ready evidence"}]), patch.object(orchestrator, "retrieve_web", side_effect=slow):
            result = asyncio.run(orchestrator.retrieve_for_query("research", "owner"))
        self.assertEqual(result["rag_results"], [{"text": "ready evidence"}])
        self.assertEqual(result["availability_notices"], [{"type": "web_unavailable"}])

    def test_transport_log_does_not_expose_provider_url_or_query(self):
        record = logging.LogRecord("httpx", logging.INFO, "", 0, "HTTP Request: %s %s", ("GET", httpx.URL(research_runtime.settings.SEARXNG_URL + "?q=private-query")), None)
        self.assertFalse(research_runtime.RedactSearchTransportLogs().filter(record))

    def test_outage_answer_has_no_claim_verification_or_provider_call(self):
        with patch.object(ai_service, "retrieve_for_query", new=AsyncMock(return_value={"route": "web", "rag_results": [], "web_results": [], "availability_notices": [{"type": "web_unavailable"}]})), patch.object(ai_service, "client") as provider:
            events = [json.loads(event) for event in ai_service.stream_response([ChatMessage(role="user", content="what is law?")], "owner", conversation_id="conversation")]
        answer = next(event["content"] for event in events if event["type"] == "token")
        self.assertIn("temporarily unavailable", answer)
        self.assertFalse(any(event["type"] == "verification" for event in events))
        status = [event for event in events if event["type"] == "availability"][-1]
        self.assertTrue(availability.verify_availability(status["receipt"], "owner", "conversation", answer)["availability_only"])
        provider.chat.completions.create.assert_not_called()

    def test_notices_are_not_evidence_prompt_or_verified_claims(self):
        chunk = SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="Supported document answer"))])
        provider = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=Mock(return_value=[chunk]))))
        items = [{"type": "web_unavailable"}]
        with patch.object(ai_service, "retrieve_for_query", new=AsyncMock(return_value={"route": "hybrid", "rag_results": [{"text": "document evidence"}], "web_results": [], "availability_notices": items})), patch.object(ai_service, "client", provider), patch.object(ai_service, "build_evidence_bundle", return_value={"evidence": []}) as bundle, patch.object(ai_service, "build_legal_prompt", return_value="grounded prompt") as prompt, patch.object(ai_service, "verify_claims", return_value={"claims": [], "summary": {"total_claims": 0}}) as verify:
            events = list(ai_service.stream_response([ChatMessage(role="user", content="research question")], "owner"))
        self.assertTrue(events)
        self.assertNotIn("availability_notices", bundle.call_args.kwargs)
        self.assertNotIn("availability_notices", prompt.call_args.kwargs)
        self.assertNotIn("temporarily unavailable", str(provider.chat.completions.create.call_args))
        self.assertNotIn("temporarily unavailable", str(verify.call_args))
