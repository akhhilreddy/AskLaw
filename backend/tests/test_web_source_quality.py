"""Deterministic source preferences; no external search or generation."""
import asyncio
import os
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "7")

from app.services import retrieval_orchestrator as orchestrator
from app.services.web_source_ranker import (
    _authority_score, _prefers_indian_sources, rank_web_sources,
)


def source(url, title="Affidavit definition"):
    return {"url": url, "title": title,
            "content": "An affidavit is a written statement of facts sworn under oath."}


class WebSourceQualityTests(unittest.TestCase):
    def test_indian_official_then_legal_publisher_then_general_then_social(self):
        urls = ["https://m.tiktok.com/affidavit", "https://www.youtube.com/affidavit",
                "https://legalvision.com.au/affidavit", "https://blog.ipleaders.in/affidavit",
                "https://district.ecourts.gov.in/affidavit"]
        ranked = rank_web_sources("What is an affidavit?", [source(url) for url in urls])
        self.assertEqual([item["url"] for item in ranked[:3]], [urls[4], urls[3], urls[2]])
        self.assertEqual(len(ranked), 5)  # Downrank, do not silently ban.

    def test_official_court_primary_source_and_legal_subdomain_authority(self):
        publisher = source("https://blog.ipleaders.in/affidavit")
        self.assertEqual(_authority_score(publisher), .72)
        ranked = rank_web_sources("What is an affidavit?", [
            publisher, source("https://api.sci.gov.in/affidavit.pdf"),
        ])
        self.assertEqual(ranked[0]["source_metadata"]["source_type"], "primary")
        self.assertEqual(ranked[0]["ranking"]["authority_score"], 1)

    def test_domain_lookalikes_and_url_paths_do_not_gain_authority(self):
        for url in ("https://ipleaders.in.evil.example/affidavit",
                    "https://fakeipleaders.in/affidavit",
                    "https://evil.example/sci.gov.in/affidavit"):
            with self.subTest(url=url):
                self.assertEqual(_authority_score(source(url)), .45)

    def test_social_subdomain_cannot_escape_penalty_with_long_keyword_snippet(self):
        social = source("https://m.youtube.com/affidavit")
        social["content"] *= 20
        ranked = rank_web_sources("What is an affidavit?", [
            social, source("https://blog.ipleaders.in/affidavit"),
        ], limit=1)
        self.assertEqual(ranked[0]["url"], "https://blog.ipleaders.in/affidavit")

    def test_non_legal_technical_query_does_not_receive_social_penalty(self):
        candidates = [{"url": url, "title": "LSTM neural networks",
                       "content": "LSTM neural networks explained with examples."}
                      for url in ("https://youtube.com/lstm", "https://example.org/lstm")]
        ranked = rank_web_sources("What is LSTM?", candidates)
        self.assertEqual(ranked[0]["ranking"]["final_score"], ranked[1]["ranking"]["final_score"])

    def test_explicit_foreign_question_does_not_get_india_preference(self):
        self.assertTrue(_prefers_indian_sources("What is an affidavit?"))
        for query in ("What is an affidavit in Australia?", "Explain bail in the UK",
                      "What is an affidavit in the United States?"):
            self.assertFalse(_prefers_indian_sources(query))

    def test_general_sources_still_available_without_indian_candidates(self):
        result = rank_web_sources("What is an affidavit?", [
            source("https://example.org/affidavit"),
        ])
        self.assertEqual(len(result), 1)

    def test_live_retrieval_path_prefers_topical_official_source_not_unrelated_official(self):
        candidates = [source("https://tiktok.com/affidavit"),
                      source("https://blog.ipleaders.in/affidavit"),
                      source("https://district.ecourts.gov.in/affidavit"),
                      {"url": "https://sci.gov.in/tender", "title": "Catering tender",
                       "content": "Supply of food and beverages for the canteen."}]
        with patch.object(orchestrator, "ensure_web_ready", new=AsyncMock(return_value=True)), patch.object(orchestrator, "search_web", new=AsyncMock(return_value={"results": candidates})) as search:
            result = asyncio.run(orchestrator.retrieve_web("What is an affidavit?", limit=2))
        self.assertEqual([item["url"] for item in result], [candidates[2]["url"], candidates[1]["url"]])
        search.assert_awaited_once()
