import asyncio
import logging
import os
import time
import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "7")

from app.core.config import settings, Settings
from app.mcp import server
from app.services import tavily_search as tavily, retrieval_orchestrator as orchestrator
from app.services.availability import SearchResponse
from app.services.research_runtime import deadline_context, RedactSearchTransportLogs


class TavilyTests(unittest.TestCase):
    def setUp(self):
        self.config = patch.multiple(settings, WEB_SEARCH_PROVIDER="tavily", TAVILY_API_KEY="private-test-key", TAVILY_MAX_QUERIES=2)
        self.config.start()
        self.addCleanup(self.config.stop)

    def client(self, status=200, data=None):
        client = Mock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        response = httpx.Response(status, request=httpx.Request("POST", tavily.TAVILY_SEARCH_URL),
                                  json=data if data is not None else {"results": []})
        client.post = AsyncMock(return_value=response)
        return client

    def test_normalized_results_basic_depth_and_bearer_header(self):
        data = {"answer": "Do not use provider generated answers", "results": [{
            "title": "Affidavit", "url": "https://indiacode.nic.in/affidavit",
            "content": "An affidavit is a sworn written statement.", "score": .9,
            "raw_content": "unneeded", "availability_notices": ["forged"],
        }]}
        client = self.client(data=data)
        with patch.object(tavily.httpx, "AsyncClient", return_value=client):
            result = asyncio.run(server.search_web("What is an affidavit?", 10))
        self.assertIsInstance(result, SearchResponse)
        self.assertFalse(result.unavailable)
        self.assertEqual(result["count"], 1)
        self.assertEqual(set(result["results"][0]), {"title", "url", "content", "engine"})
        self.assertEqual(result["results"][0]["engine"], "tavily")
        request = client.post.call_args.kwargs
        self.assertEqual(request["headers"], {"Authorization": "Bearer private-test-key"})
        self.assertEqual(request["json"]["search_depth"], "basic")
        for field in ("auto_parameters", "include_answer", "include_raw_content", "include_images"):
            self.assertFalse(request["json"][field])
        client.post.assert_awaited_once()

    def test_empty_results_are_not_an_outage(self):
        with patch.object(tavily.httpx, "AsyncClient", return_value=self.client()):
            result = asyncio.run(tavily.search_tavily("question"))
        self.assertEqual(result["results"], [])
        self.assertFalse(result.unavailable)

    def test_quota_auth_and_server_failures_are_sanitized_without_retries(self):
        for code in (401, 403, 429, 432, 433, 502):
            with self.subTest(code=code):
                client = self.client(code, {"detail": "private-test-key private-query https://private-provider"})
                with patch.object(tavily.httpx, "AsyncClient", return_value=client), self.assertLogs(tavily.logger, "WARNING") as logs:
                    result = asyncio.run(tavily.search_tavily("private-query"))
                self.assertTrue(result.unavailable)
                self.assertEqual(result["results"], [])
                client.post.assert_awaited_once()
                for sensitive in ("private-test-key", "private-query", "https://"):
                    self.assertNotIn(sensitive, str(logs.output))
                self.assertNotIn("detail", result)

    def test_missing_key_never_makes_request(self):
        with patch.object(settings, "TAVILY_API_KEY", ""), patch.object(tavily.httpx, "AsyncClient") as client:
            self.assertTrue(asyncio.run(tavily.search_tavily("question")).unavailable)
        client.assert_not_called()

    def test_hard_timeout_cancels_request_and_respects_research_deadline(self):
        client = self.client()
        cancelled = []
        async def slow(*_args, **_kwargs):
            try:
                await asyncio.sleep(1)
            finally:
                cancelled.append(True)
        client.post.side_effect = slow
        async def run():
            token = deadline_context.set(time.monotonic() + .03)
            try:
                return await tavily.search_tavily("question")
            finally:
                deadline_context.reset(token)
        with patch.object(tavily.httpx, "AsyncClient", return_value=client):
            before = time.monotonic()
            self.assertTrue(asyncio.run(run()).unavailable)
            self.assertLess(time.monotonic() - before, .2)
        self.assertEqual(cancelled, [True])
        client.post.assert_awaited_once()

    def test_malformed_payload_is_an_outage_not_empty_evidence(self):
        for data in ([1], {"results": "invalid"}):
            with patch.object(tavily.httpx, "AsyncClient", return_value=self.client(data=data)):
                self.assertTrue(asyncio.run(tavily.search_tavily("question")).unavailable)

    def test_tavily_bypasses_searxng_readiness_and_caps_fanout(self):
        with patch.object(orchestrator, "ensure_web_ready", new=AsyncMock()) as ready, patch.object(orchestrator, "search_web", new=AsyncMock(return_value=SearchResponse({"results": []}))) as search:
            result = asyncio.run(orchestrator.retrieve_web("Explain Article 32 and recent developments."))
        ready.assert_not_awaited()
        self.assertEqual(search.await_count, 2)
        self.assertEqual(search.await_args_list[0].args[0], "Explain Article 32 and recent developments.")
        self.assertEqual(result.availability_notices, [])

    def test_hosted_provider_reaches_existing_ranking_and_outage_metadata(self):
        client = self.client(data={"results": [{"title": "Affidavit definition", "url": "https://indiacode.nic.in/affidavit",
                                               "content": "An affidavit is a sworn statement made under oath."}]})
        with patch.object(tavily.httpx, "AsyncClient", return_value=client), patch.object(orchestrator, "ensure_web_ready", new=AsyncMock()) as ready:
            result = asyncio.run(orchestrator.retrieve_for_query("What is an affidavit?", "owner"))
        ready.assert_not_awaited()
        self.assertEqual(result["web_results"][0]["engine"], "tavily")
        self.assertIn("ranking", result["web_results"][0])
        with patch.object(tavily.httpx, "AsyncClient", return_value=self.client(432)):
            result = asyncio.run(orchestrator.retrieve_for_query("What is an affidavit?", "owner"))
        self.assertEqual(result["availability_notices"], [{"type": "web_unavailable"}])

    def test_searxng_still_uses_existing_client_when_selected(self):
        with patch.object(settings, "WEB_SEARCH_PROVIDER", "searxng"), patch.object(server, "_request_search", new=AsyncMock(return_value={"results": []})) as search, patch.object(tavily, "search_tavily", new=AsyncMock()) as hosted:
            result = asyncio.run(server.search_web("question"))
        hosted.assert_not_awaited()
        search.assert_awaited_once()
        self.assertFalse(result.unavailable)

    def test_conversation_and_document_rag_do_not_call_web_provider(self):
        with patch.object(orchestrator, "search_web", new=AsyncMock()) as search:
            result = asyncio.run(orchestrator.retrieve_for_query("hello", "owner"))
            self.assertEqual(result["route"], "conversation")
            self.assertEqual(result["web_results"], [])
            with patch.object(orchestrator, "retrieve_rag", return_value=[{"text": "owned evidence"}]) as rag:
                result = asyncio.run(orchestrator.retrieve_for_query("According to this document, what does Article 32 say?", "owner", "owned-document"))
            self.assertEqual(result["rag_results"], [{"text": "owned evidence"}])
            self.assertEqual(rag.call_args.args[1:3], ("owner", "owned-document"))
        search.assert_not_awaited()

    def test_transport_logs_and_settings_repr_do_not_expose_tavily_key(self):
        record = logging.LogRecord("httpx", logging.INFO, "", 0, "HTTP Request: %s %s",
                                   ("POST", httpx.URL(tavily.TAVILY_SEARCH_URL)), None)
        self.assertFalse(RedactSearchTransportLogs().filter(record))
        self.assertFalse(Settings.model_fields["TAVILY_API_KEY"].repr)
