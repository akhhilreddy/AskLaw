import asyncio
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx
from pydantic import ValidationError


os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "7")
os.environ.setdefault("GROQ_API_KEY", "test-groq-key")


from app.core.config import Settings
from app.mcp import server as mcp_server
from app.schemas.chat import ChatMessage
from app.services import ai_service
from app.services import retrieval_orchestrator
from app.services import wikipedia_service
from app.services.prompt_service import build_legal_prompt
from app.services.query_router import QueryRoute, route_query
from app.services.web_source_ranker import rank_web_sources


def make_settings(**overrides):
    values = {
        "APP_ENV": "development",
        "SECRET_KEY": "test-secret-key",
        "ALGORITHM": "HS256",
        "ACCESS_TOKEN_EXPIRE_MINUTES": 15,
        "REFRESH_TOKEN_EXPIRE_DAYS": 7,
        "EMBEDDING_PROVIDER": "local",
        "QDRANT_URL": "http://localhost:6333",
        "CORS_ORIGINS": "http://localhost:5173",
        "COOKIE_SECURE": False,
        "SEARXNG_URL": "http://127.0.0.1:8080/search",
        "FRONTEND_URL": "http://localhost:5173",
        "RESEND_API_KEY": "test-resend-key",
        "EMAIL_FROM": "AskLAW <auth@example.com>",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code < 400:
            return None

        request = httpx.Request("GET", "https://search.example.com/search")
        response = httpx.Response(self.status_code, request=request)
        response.raise_for_status()

    def json(self):
        return self.payload


class FakeAsyncClient:
    def __init__(self, response=None, error=None, responses=None):
        self.response = response
        self.error = error
        self.responses = list(responses or [])
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def get(self, url, params):
        self.requests.append((url, params))
        if self.error is not None:
            raise self.error
        if self.responses:
            return self.responses.pop(0)
        return self.response


class SearxngConfigurationTests(unittest.TestCase):
    def test_local_searxng_search_url_is_supported(self):
        settings = make_settings()
        self.assertEqual(
            settings.SEARXNG_URL,
            "http://127.0.0.1:8080/search",
        )

    def test_production_searxng_search_url_is_supported(self):
        settings = make_settings(
            APP_ENV="production",
            SECRET_KEY="x" * 32,
            COOKIE_SECURE=True,
            CORS_ORIGINS="https://asklaw.example",
            SEARXNG_URL=(
                "https://asklaw-searxng.onrender.com/search"
            ),
            FRONTEND_URL="https://asklaw.example",
        )
        self.assertEqual(
            settings.SEARXNG_URL,
            "https://asklaw-searxng.onrender.com/search",
        )

    def test_production_rejects_loopback_searxng(self):
        with self.assertRaisesRegex(
            ValidationError,
            "cannot use a loopback address in production",
        ):
            make_settings(
                APP_ENV="production",
                SECRET_KEY="x" * 32,
                COOKIE_SECURE=True,
                CORS_ORIGINS="https://asklaw.example",
            )

    def test_searxng_url_requires_exact_search_endpoint(self):
        with self.assertRaisesRegex(
            ValidationError,
            "ending exactly in /search",
        ):
            make_settings(
                SEARXNG_URL="https://asklaw-searxng.onrender.com",
            )


class SearxngMcpTests(unittest.TestCase):
    def test_search_uses_configured_endpoint_and_parses_json(self):
        client = FakeAsyncClient(
            response=FakeResponse(
                {
                    "results": [
                        {
                            "title": "Supreme Court of India",
                            "url": "https://www.sci.gov.in/",
                            "content": "Official court website",
                            "engine": "google",
                        },
                        {
                            "title": "Second result",
                            "url": "https://example.test/second",
                            "content": "Second result content",
                            "engine": "bing",
                        },
                    ]
                }
            )
        )

        with patch.object(
            mcp_server.settings,
            "SEARXNG_URL",
            "https://asklaw-searxng.onrender.com/search",
        ), patch.object(
            mcp_server.httpx,
            "AsyncClient",
            return_value=client,
        ):
            result = asyncio.run(
                mcp_server.search_web("Article 32", limit=1)
            )

        self.assertEqual(
            client.requests,
            [
                (
                    "https://asklaw-searxng.onrender.com/search",
                    {"q": "Article 32", "format": "json"},
                )
            ],
        )
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["results"][0]["engine"], "google")

    def test_search_failure_returns_safe_empty_result(self):
        client = FakeAsyncClient(
            error=httpx.ConnectError("service unavailable"),
        )

        with patch.object(
            mcp_server.httpx,
            "AsyncClient",
            return_value=client,
        ), patch.object(
            mcp_server.asyncio,
            "sleep",
        ) as sleep:
            result = asyncio.run(
                mcp_server.search_web("Article 32")
            )

        self.assertEqual(len(client.requests), 3)
        self.assertEqual(
            [call.args[0] for call in sleep.call_args_list],
            [5.0, 15.0],
        )
        self.assertEqual(result["results"], [])
        self.assertEqual(result["count"], 0)
        self.assertEqual(
            result["error"],
            "Web search is temporarily unavailable",
        )

    def test_transient_bad_gateway_is_retried_and_recovers(self):
        client = FakeAsyncClient(
            responses=[
                FakeResponse({}, status_code=502),
                FakeResponse(
                    {
                        "results": [
                            {
                                "title": "Supreme Court of India",
                                "url": "https://www.sci.gov.in/",
                                "content": "Official court website",
                                "engine": "google",
                            }
                        ]
                    }
                ),
            ]
        )

        with patch.object(
            mcp_server.httpx,
            "AsyncClient",
            return_value=client,
        ):
            with patch.object(mcp_server.asyncio, "sleep") as sleep:
                result = asyncio.run(
                    mcp_server.search_web("Article 32")
                )

        self.assertEqual(len(client.requests), 2)
        sleep.assert_awaited_once_with(5.0)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["results"][0]["engine"], "google")

    def test_existing_research_routes_are_unchanged(self):
        self.assertEqual(
            route_query("What does Article 32 provide?"),
            QueryRoute.RAG,
        )
        self.assertEqual(
            route_query("Latest Supreme Court privacy judgment"),
            QueryRoute.WEB,
        )
        self.assertEqual(
            route_query("Latest development about Article 32"),
            QueryRoute.HYBRID,
        )


class WebEvidenceQualityTests(unittest.TestCase):
    def test_unrelated_search_hits_are_not_presented_as_evidence(self):
        ranked = rank_web_sources(
            "what is an affidavit?",
            [
                {
                    "title": "Summer holiday destinations",
                    "url": "https://example.com/holidays",
                    "content": "Popular summer travel ideas.",
                },
                {
                    "title": "Affidavit definition",
                    "url": "https://example.org/affidavit",
                    "content": "An affidavit is a written statement made under oath.",
                },
            ],
        )
        self.assertEqual(
            [item["title"] for item in ranked],
            ["Affidavit definition"],
        )

    def test_retrieval_does_not_pass_unrelated_hits_to_chat(self):
        search_result = {
            "results": [{
                "title": "Summer holiday destinations",
                "url": "https://example.com/holidays",
                "content": "Popular summer travel ideas.",
            }],
        }
        with patch.object(
            retrieval_orchestrator,
            "search_web",
            new=AsyncMock(return_value=search_result),
        ):
            sources = asyncio.run(
                retrieval_orchestrator.retrieve_web("affidavit rules")
            )
        self.assertEqual(sources, [])

    def test_matching_only_the_year_is_not_topic_evidence(self):
        ranked = rank_web_sources(
            "latest Supreme Court privacy judgment 2026",
            [{
                "title": "Travel ideas for 2026",
                "url": "https://example.com/travel-2026",
                "content": "Holiday destinations this year.",
            }],
        )
        self.assertEqual(ranked, [])

    def test_prompt_names_the_actual_evidence_type(self):
        for route, expected in (
            ("rag", "The provided documents"),
            ("web", "The available web sources"),
            ("hybrid", "The available document and web sources"),
        ):
            with self.subTest(route=route):
                prompt = build_legal_prompt("What is an affidavit?", route=route)
                self.assertIn(expected, prompt)
                if route == "web":
                    self.assertNotIn("The provided documents", prompt)

    def test_no_web_evidence_returns_honest_answer_without_verification(self):
        with patch.object(
            ai_service,
            "retrieve_for_query",
            new=AsyncMock(return_value={
                "route": "web",
                "rag_results": [],
                "web_results": [],
            }),
        ), patch.object(ai_service, "client") as client:
            events = [
                json.loads(item)
                for item in ai_service.stream_response(
                    [ChatMessage(role="user", content="what is an affidavit?")],
                    user_id="user-1",
                )
            ]

        self.assertEqual([event["type"] for event in events], ["token", "route"])
        self.assertIn("web sources", events[0]["content"])
        self.assertEqual(events[1]["route"], "web")
        client.chat.completions.create.assert_not_called()

    def test_insufficient_answer_is_not_scored_as_a_legal_claim(self):
        source = rank_web_sources("what are human rights?", [{
            "title": "Wikipedia: Human rights",
            "url": "https://en.wikipedia.org/?curid=123",
            "content": "Human rights are moral principles or norms.",
            "engine": "wikipedia",
        }])
        answer = (
            "The available web sources do not contain enough information "
            "to answer that part of the question."
        )
        stream_chunk = SimpleNamespace(choices=[
            SimpleNamespace(delta=SimpleNamespace(content=answer))
        ])
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
            create=Mock(return_value=[stream_chunk])
        )))
        with patch.object(
            ai_service,
            "retrieve_for_query",
            new=AsyncMock(return_value={
                "route": "web", "rag_results": [], "web_results": source,
            }),
        ), patch.object(ai_service, "client", client):
            events = [json.loads(item) for item in ai_service.stream_response(
                [ChatMessage(role="user", content="what are human rights?")],
                user_id="user-1",
            )]

        self.assertFalse(any(item["type"] == "verification" for item in events))
        self.assertEqual(events[-1]["route"], "web")


class WikipediaDefinitionTests(unittest.TestCase):
    def test_only_simple_non_current_questions_use_definition_lookup(self):
        self.assertEqual(
            wikipedia_service.definition_subject("what is pocso act?"),
            "pocso act",
        )
        self.assertEqual(
            wikipedia_service.definition_subject("What are human rights?"),
            "human rights",
        )
        self.assertIsNone(
            wikipedia_service.definition_subject("What is the latest privacy judgment?")
        )
        self.assertIsNone(
            wikipedia_service.definition_subject("Explain Article 32")
        )

    def test_definition_lookup_returns_attributed_source_text(self):
        client = FakeAsyncClient(response=FakeResponse({
            "query": {"pages": [{
                "pageid": 123,
                "title": "Protection of Children from Sexual Offences Act, 2012",
                "extract": "The POCSO Act is an Act of Parliament of India.",
            }]},
        }))
        with patch.object(
            wikipedia_service.httpx,
            "AsyncClient",
            return_value=client,
        ):
            source = asyncio.run(
                wikipedia_service.search_wikipedia_definition("pocso act")
            )

        self.assertEqual(client.requests[0][0], wikipedia_service.WIKIPEDIA_API_URL)
        self.assertEqual(client.requests[0][1]["gsrsearch"], "pocso act")
        self.assertEqual(source["engine"], "wikipedia")
        self.assertEqual(source["url"], "https://en.wikipedia.org/?curid=123")
        self.assertIn("POCSO Act", source["content"])

    def test_definition_lookup_failure_returns_no_source(self):
        client = FakeAsyncClient(response=FakeResponse({}, status_code=503))
        with patch.object(
            wikipedia_service.httpx,
            "AsyncClient",
            return_value=client,
        ):
            source = asyncio.run(
                wikipedia_service.search_wikipedia_definition("law")
            )
        self.assertIsNone(source)

    def test_simple_definition_uses_attributed_source_not_searxng(self):
        source = {
            "title": "Wikipedia: Law",
            "url": "https://en.wikipedia.org/?curid=123",
            "content": "Law is a set of rules enforced to regulate behavior.",
            "engine": "wikipedia",
        }
        with patch.object(
            retrieval_orchestrator,
            "search_wikipedia_definition",
            new=AsyncMock(return_value=source),
        ) as wiki, patch.object(
            retrieval_orchestrator,
            "search_web",
            new=AsyncMock(),
        ) as searxng:
            results = asyncio.run(
                retrieval_orchestrator.retrieve_web("what is law?")
            )

        wiki.assert_awaited_once_with("law")
        searxng.assert_not_called()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["engine"], "wikipedia")

    def test_failed_definition_lookup_does_not_emit_unrelated_sources(self):
        with patch.object(
            retrieval_orchestrator,
            "search_wikipedia_definition",
            new=AsyncMock(return_value=None),
        ), patch.object(
            retrieval_orchestrator,
            "search_web",
            new=AsyncMock(),
        ) as searxng:
            results = asyncio.run(
                retrieval_orchestrator.retrieve_web("what is law?")
            )

        self.assertEqual(results, [])
        searxng.assert_not_called()

    def test_current_web_research_keeps_searxng_path(self):
        with patch.object(
            retrieval_orchestrator,
            "search_wikipedia_definition",
            new=AsyncMock(),
        ) as wiki, patch.object(
            retrieval_orchestrator,
            "search_web",
            new=AsyncMock(return_value={"results": []}),
        ) as searxng:
            asyncio.run(
                retrieval_orchestrator.retrieve_web(
                    "What is the latest privacy judgment?"
                )
            )

        wiki.assert_not_called()
        searxng.assert_called()

    def test_definition_evidence_flows_to_answer_and_verification(self):
        source = rank_web_sources("what is law?", [{
            "title": "Wikipedia: Law",
            "url": "https://en.wikipedia.org/?curid=123",
            "content": (
                "Law is a set of rules that are created and enforced by "
                "governmental or societal institutions to regulate behavior."
            ),
            "engine": "wikipedia",
        }])
        answer = (
            "Law is a set of rules created and enforced by governmental "
            "or societal institutions to regulate behavior."
        )
        stream_chunk = SimpleNamespace(choices=[
            SimpleNamespace(delta=SimpleNamespace(content=answer))
        ])
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
            create=Mock(return_value=[stream_chunk])
        )))

        with patch.object(
            ai_service,
            "retrieve_for_query",
            new=AsyncMock(return_value={
                "route": "web", "rag_results": [], "web_results": source,
            }),
        ), patch.object(ai_service, "client", client):
            events = [json.loads(item) for item in ai_service.stream_response(
                [ChatMessage(role="user", content="what is law?")],
                user_id="user-1",
            )]

        sources_event = next(item for item in events if item["type"] == "sources")
        verification = next(item for item in events if item["type"] == "verification")
        self.assertEqual(sources_event["sources"][0]["engine"], "wikipedia")
        self.assertEqual(verification["grounding_score"], 1.0)
        self.assertEqual(events[-1]["route"], "web")


if __name__ == "__main__":
    unittest.main()
