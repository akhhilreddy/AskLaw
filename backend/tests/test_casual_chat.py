import asyncio
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx
from qdrant_client.http.exceptions import UnexpectedResponse


os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "7")
os.environ.setdefault("GROQ_API_KEY", "test-groq-key")


from app.schemas.chat import ChatMessage
from app.services import ai_service, retrieval_orchestrator
from app.services.query_router import QueryRoute, route_query


class CasualChatRoutingTests(unittest.TestCase):
    def test_clear_greetings_and_thanks_are_conversational(self):
        for query in (
            "hello",
            "Hi!",
            "hey there",
            "good morning",
            "thanks",
            "Thank you",
        ):
            with self.subTest(query=query):
                self.assertEqual(route_query(query), QueryRoute.CONVERSATION)

    def test_legal_question_keeps_rag_route(self):
        query = "What does Article 32 provide?"

        with patch.object(
            retrieval_orchestrator,
            "retrieve_rag",
            return_value=[{"text": "Article 32 evidence"}],
        ) as retrieve_rag:
            result = asyncio.run(
                retrieval_orchestrator.retrieve_for_query(
                    query=query,
                    user_id="user-1",
                )
            )

        self.assertEqual(route_query(query), QueryRoute.RAG)
        self.assertEqual(result["route"], "rag")
        retrieve_rag.assert_called_once_with(
            query,
            "user-1",
            None,
            5,
        )
        self.assertEqual(
            route_query("Hello, what does Article 32 provide?"),
            QueryRoute.RAG,
        )

    def test_document_specific_question_keeps_document_scoped_retrieval(self):
        with patch.object(
            retrieval_orchestrator,
            "retrieve_rag",
            return_value=[{"document_id": "doc-1", "text": "Evidence"}],
        ) as retrieve_rag, patch.object(
            retrieval_orchestrator,
            "retrieve_web",
        ) as retrieve_web:
            result = asyncio.run(
                retrieval_orchestrator.retrieve_for_query(
                    query="What does this document say about remedies?",
                    user_id="user-1",
                    document_id="doc-1",
                )
            )

        self.assertEqual(result["route"], "rag")
        retrieve_rag.assert_called_once_with(
            "What does this document say about remedies?",
            "user-1",
            "doc-1",
            5,
        )
        retrieve_web.assert_not_called()

    def test_unscoped_empty_rag_falls_back_to_web(self):
        web_evidence = [
            {
                "title": "Article 32",
                "url": "https://example.test/article-32",
                "content": "Article 32 guarantees constitutional remedies.",
            }
        ]

        with patch.object(
            retrieval_orchestrator,
            "retrieve_rag",
            return_value=[],
        ) as retrieve_rag, patch.object(
            retrieval_orchestrator,
            "retrieve_web",
            new=AsyncMock(return_value=web_evidence),
        ) as retrieve_web:
            result = asyncio.run(
                retrieval_orchestrator.retrieve_for_query(
                    query="What does Article 32 provide?",
                    user_id="user-1",
                )
            )

        retrieve_rag.assert_called_once_with(
            "What does Article 32 provide?",
            "user-1",
            None,
            5,
        )
        retrieve_web.assert_awaited_once_with(
            "What does Article 32 provide?",
            5,
        )
        self.assertEqual(result["route"], "web")
        self.assertEqual(result["rag_results"], [])
        self.assertEqual(result["web_results"], web_evidence)

    def test_document_scoped_empty_rag_does_not_fall_back_to_web(self):
        with patch.object(
            retrieval_orchestrator,
            "retrieve_rag",
            return_value=[],
        ), patch.object(
            retrieval_orchestrator,
            "retrieve_web",
            new=AsyncMock(),
        ) as retrieve_web:
            result = asyncio.run(
                retrieval_orchestrator.retrieve_for_query(
                    query="What does Article 32 provide?",
                    user_id="user-1",
                    document_id="doc-1",
                )
            )

        retrieve_web.assert_not_awaited()
        self.assertEqual(result["route"], "rag")
        self.assertEqual(result["rag_results"], [])
        self.assertEqual(result["web_results"], [])

    def test_missing_qdrant_collection_is_treated_as_empty_rag(self):
        missing_collection = UnexpectedResponse(
            status_code=404,
            reason_phrase="Not Found",
            content=b"collection does not exist",
            headers=httpx.Headers(),
        )

        with patch.object(
            retrieval_orchestrator,
            "retrieve_relevant_chunks",
            side_effect=missing_collection,
        ):
            result = retrieval_orchestrator.retrieve_rag(
                "What does Article 32 provide?",
                "user-1",
            )

        self.assertEqual(result, [])

    def test_unrelated_qdrant_not_found_error_is_not_hidden(self):
        unrelated_not_found = UnexpectedResponse(
            status_code=404,
            reason_phrase="Not Found",
            content=b"route not found",
            headers=httpx.Headers(),
        )

        with patch.object(
            retrieval_orchestrator,
            "retrieve_relevant_chunks",
            side_effect=unrelated_not_found,
        ):
            with self.assertRaises(UnexpectedResponse):
                retrieval_orchestrator.retrieve_rag(
                    "What does Article 32 provide?",
                    "user-1",
                )

    def test_casual_stream_has_no_research_metadata(self):
        stream_chunk = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(
                        content="Hello! How can I assist you today?",
                    )
                )
            ]
        )
        client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=Mock(return_value=[stream_chunk]),
                )
            )
        )

        with patch.object(
            retrieval_orchestrator,
            "retrieve_rag",
        ) as retrieve_rag, patch.object(
            retrieval_orchestrator,
            "retrieve_web",
        ) as retrieve_web, patch.object(
            ai_service,
            "build_evidence_bundle",
        ) as build_evidence, patch.object(
            ai_service,
            "build_legal_prompt",
        ) as build_prompt, patch.object(
            ai_service,
            "verify_claims",
        ) as verify_claims, patch.object(
            ai_service,
            "client",
            client,
        ):
            events = [
                json.loads(item)
                for item in ai_service.stream_response(
                    [ChatMessage(role="user", content="hello")],
                    user_id="user-1",
                )
            ]

        self.assertEqual(
            [event["type"] for event in events],
            ["token", "route"],
        )
        self.assertEqual(events[-1]["route"], "conversation")
        retrieve_rag.assert_not_called()
        retrieve_web.assert_not_called()
        build_evidence.assert_not_called()
        build_prompt.assert_not_called()
        verify_claims.assert_not_called()


if __name__ == "__main__":
    unittest.main()
