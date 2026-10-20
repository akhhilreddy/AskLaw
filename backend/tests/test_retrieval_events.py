import asyncio
import json
import threading
import unittest
from unittest.mock import AsyncMock, Mock, patch
from concurrent.futures import ThreadPoolExecutor

from app.services import ai_service
from app.services.research_runtime import progress
from app.services.retrieval_events import retrieval_events
from app.schemas.chat import ChatMessage
from app.api.chat import ClosingStreamingResponse
from starlette.requests import ClientDisconnect


class RetrievalEventTests(unittest.TestCase):
    def test_asgi_disconnect_cancels_provider_worker_and_logs_correlation(self):
        from types import SimpleNamespace
        closed = threading.Event()
        def chunks():
            try:
                while True:
                    yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="partial"))])
            finally:
                closed.set()
        async def send(event):
            if event["type"] == "http.response.body":
                raise OSError("private transport error")
        async def receive():
            return {"type": "http.disconnect"}
        async def exercise():
            response = ClosingStreamingResponse(ai_service.stream_response([ChatMessage(role="user", content="hello")], "owner", request_id="fixture-correlation"), request_id="fixture-correlation", media_type="application/x-ndjson")
            with self.assertRaises(ClientDisconnect):
                await response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send)
        with patch.object(ai_service.client.chat.completions, "create", return_value=chunks()), self.assertLogs("app.api.chat", level="INFO") as logs:
            asyncio.run(exercise())
        self.assertTrue(closed.wait(1))
        self.assertIn("fixture-correlation", str(logs.output))
        self.assertIn("interrupted", str(logs.output))
        self.assertNotIn("private", str(logs.output))

    def test_iterator_can_resume_on_different_streaming_worker_threads(self):
        async def retrieval():
            progress("web_waking")
            await asyncio.sleep(.08)
            progress("web_ready")
            return {"route": "web"}
        iterator = retrieval_events(retrieval())
        with ThreadPoolExecutor(max_workers=1) as first, ThreadPoolExecutor(max_workers=1) as second:
            self.assertEqual(first.submit(next, iterator).result(timeout=1)["code"], "web_waking")
            self.assertEqual(second.submit(next, iterator).result(timeout=1)["code"], "web_ready")
            self.assertEqual(second.submit(next, iterator).result(timeout=1)["result"], {"route": "web"})
            second.submit(iterator.close).result(timeout=1)
    def test_progress_precedes_answer_and_source_only_notices_skip_verification(self):
        async def retrieval(**_kwargs):
            progress("web_waking")
            await asyncio.sleep(.08)
            progress("web_unavailable")
            return {"route": "web", "rag_results": [], "web_results": [],
                    "availability_notices": [{"type": "web_unavailable"}]}
        with patch.object(ai_service, "retrieve_for_query", side_effect=retrieval), patch.object(ai_service, "client") as provider:
            events = [json.loads(event) for event in ai_service.stream_response([ChatMessage(role="user", content="what is law?")], "owner")]
        self.assertEqual(events[0], {"type": "progress", "code": "web_waking"})
        self.assertTrue(any(event["type"] == "token" for event in events))
        self.assertFalse(any(event["type"] == "verification" for event in events))
        provider.chat.completions.create.assert_not_called()

    def test_closing_generator_cancels_async_retrieval(self):
        cancelled = threading.Event()
        async def retrieval():
            try:
                progress("web_waking")
                await asyncio.sleep(10)
            finally:
                cancelled.set()
        iterator = retrieval_events(retrieval())
        self.assertEqual(next(iterator)["code"], "web_waking")
        iterator.close()
        self.assertTrue(cancelled.is_set())

    def test_asgi_disconnect_closes_retrieval_and_does_not_leave_a_loop_running(self):
        cancelled = threading.Event()
        async def retrieval(**_kwargs):
            try:
                progress("web_waking")
                await asyncio.sleep(10)
            finally:
                cancelled.set()
        async def send(event):
            if event["type"] == "http.response.body":
                raise OSError("disconnected")
        async def receive():
            return {"type": "http.disconnect"}
        async def exercise():
            response = ClosingStreamingResponse(ai_service.stream_response([ChatMessage(role="user", content="research")], "owner"), media_type="application/x-ndjson")
            try:
                await response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send)
            except Exception:
                pass
        with patch.object(ai_service, "retrieve_for_query", side_effect=retrieval):
            asyncio.run(exercise())
        self.assertTrue(cancelled.is_set())
