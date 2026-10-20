"""Benchmark accounting tests; no provider, cloud account or network access."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from evaluation.measure_resume import (
    StreamObservation, distribution, failure_diagnostic, intake_summary, run_intake,
    score_intake, summarize_web, web_request, run_web, measure,
)


class ResumeMetricsTests(unittest.TestCase):
    def test_failure_diagnostics_never_expose_exception_text_or_urls(self):
        cause = httpx.RemoteProtocolError("private https://provider.invalid/?secret=value")
        wrapped = RuntimeError("api-key and private description")
        wrapped.__cause__ = cause
        self.assertEqual(failure_diagnostic(wrapped), {"category": "remote_protocol_error"})
        response = httpx.Response(429, request=httpx.Request("POST", "https://provider.invalid/?secret=value"))
        error = httpx.HTTPStatusError("private body", request=response.request, response=response)
        self.assertEqual(failure_diagnostic(error), {"category": "http_status", "http_status": 429})
        self.assertEqual(failure_diagnostic(TimeoutError("secret")), {"category": "timeout"})
        self.assertEqual(failure_diagnostic(RuntimeError("secret")), {"category": "unclassified"})

    def test_expected_fact_recall_counts_unavailable_calls_as_missing(self):
        score = {"field_true_positive": 1, "field_false_positive": 0, "field_false_negative": 0, "scope_pass": True}
        rows = [{"status": "ok", "elapsed_seconds": 1, "score": score, "expected_fact_count": 1},
                {"status": "unavailable", "elapsed_seconds": 25, "expected_fact_count": 3}]
        result = intake_summary(rows)
        self.assertEqual(result["micro_recall"], 1)
        self.assertEqual(result["planned_expected_facts"], 4)
        self.assertEqual(result["end_to_end_expected_fact_recall"], .25)

    def test_distribution_does_not_invent_zero_or_small_sample_percentiles(self):
        self.assertEqual(distribution([]), {"n": 0, "min_seconds": None, "median_seconds": None, "max_seconds": None})
        self.assertEqual(distribution([4, 1, 3, 2]), {"n": 4, "min_seconds": 1, "median_seconds": 2.5, "max_seconds": 4})
        self.assertNotIn("p95", distribution([1]))

    def test_progress_is_not_first_answer_and_200_without_sources_is_not_success(self):
        item = StreamObservation()
        item.consume({"type": "progress", "code": "research_pending"}, .01)
        self.assertIsNone(item.first_answer_seconds)
        item.consume({"type": "token", "content": "Fictional answer."}, 2)
        result = item.result(3, 200)
        self.assertEqual(result["first_answer_seconds"], 2)
        self.assertEqual(result["status"], "failed")
        self.assertNotIn("answer", result)

    def test_success_retains_metadata_but_removes_answer_and_url_queries(self):
        item = StreamObservation()
        item.consume({"type": "token", "content": "Fictional answer."}, 2)
        item.consume({"type": "sources", "sources": [{"url": "https://example.invalid/page?query=secret"}]}, 3)
        item.consume({"type": "route", "route": "web"}, 3)
        result = item.result(4, 200)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["source_domains"], ["example.invalid"])
        self.assertNotIn("secret", str(result))
        self.assertNotIn("Fictional answer", str(result))

    def test_stream_errors_outages_and_insufficient_responses_never_count_as_success(self):
        from app.services.prompt_service import insufficient_evidence_message
        for event in [{"type": "error"}, {"type": "availability", "notices": [{"type": "web_unavailable"}]}]:
            item = StreamObservation()
            item.consume({"type": "token", "content": "Answer"}, 1)
            item.consume({"type": "sources", "sources": [{"url": "https://example.invalid"}]}, 2)
            item.consume(event, 2)
            self.assertNotEqual(item.result(3, 200)["status"], "ok")
        item = StreamObservation()
        item.consume({"type": "token", "content": insufficient_evidence_message("web")}, 1)
        self.assertTrue(item.result(2, 200)["insufficient_evidence"])

    def test_clean_eof_before_final_route_is_incomplete_even_with_sources(self):
        item = StreamObservation()
        item.consume({"type": "token", "content": "Answer"}, 1)
        item.consume({"type": "sources", "sources": [{"url": "https://example.invalid"}]}, 2)
        self.assertEqual(item.result(3, 200)["status"], "failed")
        self.assertFalse(item.result(3, 200)["terminal_route_received"])
        item.consume({"type": "route", "route": "web"}, 3)
        self.assertEqual(item.result(4, 200)["status"], "ok")

    def test_web_summary_keeps_failures_and_first_answer_excludes_progress(self):
        rows = [{"status": "ok", "first_answer_seconds": 2, "elapsed_seconds": 4},
                {"status": "request_failed", "elapsed_seconds": 90}, {"status": "not_run_setup_failed"}]
        result = summarize_web(rows)
        self.assertEqual(result["planned"], 3)
        self.assertEqual(result["completed_with_answer_and_sources"], 1)
        self.assertEqual(result["all_attempt_completion"]["max_seconds"], 90)
        self.assertEqual(result["successful_first_answer"]["median_seconds"], 2)

    def test_field_matching_penalizes_missing_and_extra_values(self):
        case = {"supported": True, "description": "Laptop INR 10. Unknown date.",
                "expected_fields": {"product": ["Laptop"], "amount_inr": ["10.00"]}, "allowed_event_dates": []}
        response = {"supported": True, "suggestions": [
            {"field": "product", "value": "laptop", "quote": "Laptop"},
            {"field": "seller_name", "value": "Invented", "quote": "Invented"},
            {"event": {"occurred_on": "2026-01-01"}, "quote": "Unknown date"}]}
        score = score_intake(case, response)
        self.assertEqual((score["field_true_positive"], score["field_false_positive"], score["field_false_negative"]), (1, 1, 1))
        self.assertEqual(score["quote_exact"], 2)
        self.assertFalse(score["dates_not_invented"])

    def test_failed_intake_is_not_silently_removed_from_scope_denominator(self):
        case = {"supported": False, "description": "Out of scope", "expected_fields": {}, "allowed_event_dates": []}
        score = score_intake(case, {"supported": False, "suggestions": []})
        rows = [{"status": "ok", "elapsed_seconds": 1, "score": score}, {"status": "unavailable", "elapsed_seconds": 25}]
        result = intake_summary(rows)
        self.assertEqual(result["scope_passes"], 1)
        self.assertEqual(result["scope_denominator"], 2)
        self.assertEqual(result["field_metrics_response_denominator"], 1)
        self.assertIsNone(result["micro_precision"])
        self.assertIsNone(result["micro_recall"])


class ResumeLiveAccountingTests(unittest.IsolatedAsyncioTestCase):
    async def test_health_budget_is_recorded_and_setup_failure_never_creates_guest(self):
        client = SimpleNamespace(get=AsyncMock(side_effect=TimeoutError("private")), post=AsyncMock())
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=client)
        context.__aexit__ = AsyncMock(return_value=False)
        with patch("evaluation.measure_resume.httpx.AsyncClient", return_value=context), patch("evaluation.measure_resume.asyncio.timeout", wraps=__import__("asyncio").timeout) as timeout:
            result = await run_web([{"id": "fixture"}], health_timeout_seconds=100)
        timeout.assert_called_once_with(100)
        self.assertEqual(client.get.call_args.kwargs["timeout"].read, 100)
        self.assertEqual(client.get.call_args.kwargs["timeout"].connect, 5)
        client.post.assert_not_awaited()
        self.assertEqual(result["rows"], [{"id": "fixture", "status": "not_run_setup_failed"}])
        self.assertEqual(result["preflight"]["failure"], {"category": "timeout"})

    async def test_web_only_skips_intake_and_reports_changed_budget(self):
        with patch("evaluation.measure_resume.run_web", new=AsyncMock(return_value={"rows": []})) as web, patch("evaluation.measure_resume.run_intake", new=AsyncMock()) as intake:
            result = await measure(True, web_only=True, health_timeout_seconds=100)
        intake.assert_not_awaited()
        self.assertEqual(web.call_args.args[1], 100)
        self.assertNotIn("intake", result)
        self.assertEqual(result["measurement_settings"]["health_timeout_seconds"], 100)
        self.assertEqual(result["measurement_settings"]["live_section"], "web")

    async def test_invalid_health_budget_refused_before_network(self):
        with patch("evaluation.measure_resume.httpx.AsyncClient") as client:
            for budget in (0, 121, float("inf")):
                with self.assertRaises(ValueError):
                    await run_web([{"id": "fixture"}], budget)
        client.assert_not_called()

    async def test_interrupted_stream_keeps_partial_timing_but_is_not_success(self):
        async def lines():
            yield '{"type":"token","content":"Partial answer"}'
            raise httpx.RemoteProtocolError("secret body")
        response = SimpleNamespace(status_code=200, aiter_lines=lines)
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=response)
        context.__aexit__ = AsyncMock(return_value=False)
        client = SimpleNamespace(stream=MagicMock(return_value=context))
        result = await web_request(client, "private-token", {"id": "fixture", "query": "fictional question"})
        self.assertEqual(result["status"], "request_failed")
        self.assertEqual(result["answer_characters"], len("Partial answer"))
        self.assertIsNotNone(result["first_answer_seconds"])
        self.assertEqual(result["failure"], {"category": "remote_protocol_error"})
        self.assertNotIn("private-token", str(result))
        self.assertNotIn("secret body", str(result))

    async def test_extractor_observation_preserves_behavior_and_restores_callable(self):
        from app.services import complaint_intake as service
        provider = AsyncMock(side_effect=[httpx.ConnectError("secret"), service.Extraction(
            scope="out_of_scope", scope_excerpt="Wages dispute", facts=[], events=[])])
        cases = [{"id": "fixture-failed", "description": "Fictional damaged laptop", "supported": True,
                  "expected_fields": {"product": ["laptop"]}, "allowed_event_dates": []},
                 {"id": "fixture-out-of-scope", "description": "Wages dispute", "supported": False,
                  "expected_fields": {}, "allowed_event_dates": []}]
        with patch.object(service.settings, "GROQ_API_KEY", "test-only"), patch.object(service, "_extract", new=provider), patch("evaluation.measure_resume.asyncio.sleep", new=AsyncMock()):
            rows = await run_intake(cases)
            self.assertIs(service._extract, provider)
        self.assertEqual(provider.await_count, 2)
        self.assertEqual(rows[0]["failure"], {"category": "network_error"})
        self.assertEqual(rows[1]["status"], "ok")
        self.assertTrue(rows[1]["score"]["scope_pass"])
        self.assertEqual(intake_summary(rows)["end_to_end_expected_fact_recall"], 0)
