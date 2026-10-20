from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
import json
import logging
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import httpx
from groq import RateLimitError

from app.services.generation_runtime import GenerationPool, GenerationBusy, GenerationTimeout, retry_delay, ProviderTransportLogFilter
from app.services import ai_service
from app.schemas.chat import ChatMessage


def rate_limit(wait="1"):
    response = httpx.Response(429, headers={"retry-after": wait}, request=httpx.Request("POST", "https://private.invalid/?secret=hidden"))
    return RateLimitError("private provider error body", response=response, body={"secret": "private"})


def chunk(text="answer"):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text))])


class GenerationRuntimeTests(unittest.TestCase):
    def events(self, pool, create, **options):
        return pool.events(create, request_id="fixture", budget=options.get("budget", 2),
                           request_timeout=.5, max_retry_wait=options.get("max_retry_wait", 1), heartbeat=.01)

    def test_short_429_wait_has_progress_then_success_and_only_one_retry(self):
        provider = Mock(side_effect=[rate_limit(), [chunk()]])
        with self.assertLogs("app.services.generation_runtime", level="INFO") as logs:
            events = list(self.events(GenerationPool(1), provider))
        self.assertEqual(provider.call_count, 2)
        self.assertTrue(any(event.get("code") == "provider_retrying" for event in events))
        self.assertEqual([e["content"] for e in events if e["type"] == "token"], ["answer"])
        self.assertNotIn("private", str(logs.output))
        self.assertEqual(provider.call_args.args[0].connect, .5)

    def test_retry_after_larger_than_cap_or_remaining_budget_is_not_shortened(self):
        for options in ({"max_retry_wait": 1}, {"budget": .05, "max_retry_wait": 30}):
            provider = Mock(side_effect=rate_limit("24"))
            with self.assertRaises(GenerationBusy):
                list(self.events(GenerationPool(1), provider, **options))
            self.assertEqual(provider.call_count, 1)

    def test_two_429s_exhaust_retry_without_third_request(self):
        provider = Mock(side_effect=rate_limit())
        with patch("app.services.generation_runtime.retry_delay", return_value=.01):
            with self.assertRaises(GenerationBusy):
                list(self.events(GenerationPool(1), provider))
        self.assertEqual(provider.call_count, 2)

    def test_deadline_returns_promptly_but_blocked_worker_keeps_slot(self):
        release, finished = threading.Event(), threading.Event()
        def provider(_timeout):
            release.wait(2)
            finished.set()
            return [chunk("late")]
        pool = GenerationPool(1)
        started = time.monotonic()
        try:
            with self.assertRaises(GenerationTimeout):
                list(self.events(pool, provider, budget=.05))
            self.assertLess(time.monotonic() - started, .5)
            for _ in range(5):
                with self.assertRaises(GenerationBusy):
                    list(self.events(pool, Mock()))
        finally:
            release.set()
            self.assertTrue(finished.wait(1))

    def test_disconnect_during_retry_stops_without_another_provider_call(self):
        provider = Mock(side_effect=rate_limit())
        pool = GenerationPool(1)
        events = self.events(pool, provider)
        self.assertEqual(next(events)["code"], "provider_retrying")
        events.close()
        self.assertEqual(provider.call_count, 1)
        # Worker retains its slot until its own finally completes.
        self.assertTrue(pool.slots.acquire(timeout=1))
        pool.slots.release()

    def test_close_closes_stream_and_iterator_can_resume_on_different_threads(self):
        closed = threading.Event()
        def stream():
            try:
                for _ in range(100):
                    yield chunk()
            finally:
                closed.set()
        pool = GenerationPool(1)
        events = self.events(pool, lambda _timeout: stream())
        with ThreadPoolExecutor(1) as first, ThreadPoolExecutor(1) as second:
            self.assertEqual(first.submit(next, events).result(timeout=1)["type"], "token")
            self.assertEqual(second.submit(next, events).result(timeout=1)["type"], "token")
            second.submit(events.close).result(timeout=1)
        self.assertTrue(closed.wait(1))
        self.assertTrue(pool.slots.acquire(timeout=1))
        pool.slots.release()

    def test_no_retry_after_partial_generation(self):
        def stream():
            yield chunk("partial")
            raise rate_limit()
        provider = Mock(return_value=stream())
        events = self.events(GenerationPool(1), provider)
        self.assertEqual(next(events)["content"], "partial")
        with self.assertRaises(RateLimitError):
            list(events)
        self.assertEqual(provider.call_count, 1)

    def test_http_date_and_invalid_retry_headers(self):
        self.assertGreater(retry_delay(rate_limit(format_datetime(datetime.now(timezone.utc) + timedelta(seconds=20)))), 18)
        for invalid in ("nan", "inf", "-2", "broken"):
            self.assertEqual(retry_delay(rate_limit(invalid)), 1)

    def test_ai_returns_clear_busy_error_and_no_terminal_success(self):
        with patch.object(ai_service.client.chat.completions, "create", side_effect=rate_limit("600")), patch.object(ai_service.logger, "warning") as warning:
            events = [json.loads(line) for line in ai_service.stream_response([ChatMessage(role="user", content="hello")], "fixture", request_id="test-correlation")]
        self.assertEqual(events[-1]["code"], "generation_busy")
        self.assertIn("rate-limited", events[-1]["content"])
        self.assertFalse(any(e["type"] == "route" for e in events))
        self.assertNotIn("private", str(events))
        self.assertIn("test-correlation", str(warning.call_args))

    def test_sdk_retries_disabled_for_chat_client(self):
        self.assertEqual(ai_service.client.max_retries, 0)

    def test_provider_transport_logs_do_not_print_urls(self):
        record = logging.LogRecord("httpx", logging.INFO, "", 1, "HTTP Request: %s %s", ("POST", httpx.URL("https://api.groq.com/path?secret=value")), None)
        self.assertFalse(ProviderTransportLogFilter().filter(record))

    def test_thread_start_failure_releases_worker_slot(self):
        pool = GenerationPool(1)
        with patch("app.services.generation_runtime.threading.Thread.start", side_effect=RuntimeError("fixture")):
            with self.assertRaises(RuntimeError):
                list(self.events(pool, Mock()))
        self.assertTrue(pool.slots.acquire(timeout=.1))
        pool.slots.release()
