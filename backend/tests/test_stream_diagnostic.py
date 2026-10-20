import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from evaluation.diagnose_stream import observe
from app.schemas.chat import ChatMessage
from app.services import ai_service


class StreamDiagnosticTests(unittest.IsolatedAsyncioTestCase):
    async def run_stream(self, events, failure=None, headers=None):
        async def lines():
            for event in events:
                yield json.dumps(event)
            if failure:
                raise failure
        response = SimpleNamespace(status_code=200, http_version="HTTP/1.1", headers=headers or {}, raise_for_status=lambda: None, aiter_lines=lines)
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=response)
        context.__aexit__ = AsyncMock(return_value=False)
        return await observe(SimpleNamespace(stream=MagicMock(return_value=context)), "private-token", {"id": "fixture", "query": "private query"})

    async def test_read_failure_after_partial_answer_is_not_provider_error_or_success(self):
        result = await self.run_stream([{"type": "token", "content": "private answer"}], httpx.ReadError("secret https://private.invalid"), headers={"x-request-id": "private untrusted header"})
        self.assertEqual(result["stage"], "stream_body")
        self.assertEqual(result["transport_kind"], "read_error")
        self.assertEqual(result["status"], "request_failed")
        self.assertEqual(result["event_counts"], {"token": 1})
        self.assertEqual(result["stream_errors"], 0)
        self.assertNotIn("private", str(result))
        self.assertNotIn("secret", str(result))

    async def test_provider_error_event_differs_from_transport_failure(self):
        result = await self.run_stream([{"type": "token", "content": "partial"}, {"type": "error", "content": "safe error"}])
        self.assertEqual(result["stage"], "closed")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["stream_errors"], 1)
        self.assertNotIn("transport_kind", result)

    async def test_complete_sources_and_route_count_as_completed(self):
        result = await self.run_stream([{"type": "token", "content": "answer"},
                                        {"type": "sources", "sources": [{"url": "https://example.invalid"}]},
                                        {"type": "route", "route": "web"}], headers={"x-request-id": "a" * 32})
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["event_counts"], {"token": 1, "sources": 1, "route": 1})
        self.assertEqual(result["http_version"], "HTTP/1.1")
        self.assertEqual(result["request_id"], "a" * 32)


class ProviderStreamFailureTests(unittest.TestCase):
    def test_groq_failure_is_sanitized_error_event_not_uncaught_disconnect(self):
        def chunks():
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="Partial answer"))])
            raise httpx.ReadError("private provider response")
        with patch.object(ai_service.client.chat.completions, "create", return_value=chunks()), patch.object(ai_service.logger, "exception"):
            events = [json.loads(line) for line in ai_service.stream_response([ChatMessage(role="user", content="hello")], "fixture-owner")]
        self.assertEqual([event["type"] for event in events], ["token", "error"])
        self.assertIn("interrupted", events[-1]["content"])
        self.assertNotIn("private", str(events))
