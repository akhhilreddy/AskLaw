import asyncio
import os
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, Mock, patch

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "7")
from app.core.config import settings
from app.services import research_runtime as runtime, retrieval_orchestrator as orchestrator


class ReadinessTests(unittest.TestCase):
    def test_two_event_loops_share_one_probe(self):
        state = runtime.SharedWebReadiness()
        started = threading.Event()
        finish = threading.Event()
        probe = Mock(side_effect=lambda *_args: (started.set(), finish.wait(2), True)[-1])
        try:
            with patch.object(state, "_probe", probe), ThreadPoolExecutor(max_workers=2) as callers:
                first = callers.submit(lambda: asyncio.run(state.ensure()))
                self.assertTrue(started.wait(1))
                second = callers.submit(lambda: asyncio.run(state.ensure()))
                time.sleep(.02)
                finish.set()
                self.assertTrue(first.result(timeout=2))
                self.assertTrue(second.result(timeout=2))
            self.assertEqual(probe.call_count, 1)
        finally:
            finish.set()
            state.executor.shutdown(wait=True)

    def test_cold_start_then_success_and_idle_reprobe(self):
        state = runtime.SharedWebReadiness()
        client = Mock()
        client.__enter__ = Mock(return_value=client)
        client.__exit__ = Mock(return_value=False)
        client.get.side_effect = [Mock(status_code=502), Mock(status_code=200), Mock(status_code=200)]
        try:
            with patch.object(runtime.httpx, "Client", return_value=client), patch.object(runtime.time, "sleep"):
                self.assertTrue(asyncio.run(state.ensure()))
                self.assertTrue(asyncio.run(state.ensure()))
                state.ready_at = time.monotonic() - settings.SEARXNG_IDLE_REPROBE_SECONDS - 1
                self.assertTrue(asyncio.run(state.ensure()))
            self.assertEqual(client.get.call_count, 3)
            self.assertTrue(client.get.call_args.args[0].endswith("/healthz"))
        finally:
            state.executor.shutdown(wait=True)

    def test_readiness_timeout_does_not_search(self):
        with patch.object(orchestrator, "ensure_web_ready", new=AsyncMock(return_value=False)), patch.object(orchestrator, "search_web", new=AsyncMock()) as search:
            self.assertEqual(asyncio.run(orchestrator.retrieve_web("what is law?")), [])
        search.assert_not_awaited()

    def test_readiness_wait_is_bounded_even_if_probe_thread_is_late(self):
        state = runtime.SharedWebReadiness()
        finish = threading.Event()
        try:
            with patch.object(state, "_probe", side_effect=lambda *_args: finish.wait(1)), patch.object(settings, "SEARXNG_READINESS_BUDGET_SECONDS", .03):
                before = time.monotonic()
                self.assertFalse(asyncio.run(state.ensure()))
                self.assertLess(time.monotonic() - before, .2)
        finally:
            finish.set()
            state.executor.shutdown(wait=True)


class RagBoundTests(unittest.TestCase):
    def test_timed_out_threads_hold_slots_until_finished_and_late_results_are_discarded(self):
        pool = runtime.BoundedRagPool(workers=1)
        finish = threading.Event()
        started = threading.Event()
        calls = []
        def rag(user_id, document_id):
            calls.append((user_id, document_id))
            started.set()
            finish.wait(2)
            return ["late evidence"]
        async def exercise():
            token = runtime.deadline_context.set(time.monotonic() + .03)
            try:
                with self.assertRaises(TimeoutError):
                    await pool.run(rag, "owner", "owned-doc")
                self.assertTrue(started.is_set())
                for _ in range(5):
                    with self.assertRaises(runtime.RagUnavailable):
                        await pool.run(rag, "other", "different-doc")
            finally:
                runtime.deadline_context.reset(token)
        try:
            asyncio.run(exercise())
            self.assertEqual(calls, [("owner", "owned-doc")])
        finally:
            finish.set()
            pool.executor.shutdown(wait=True)
        self.assertTrue(pool.slots.acquire(blocking=False))
        pool.slots.release()

    def test_overall_deadline_bounds_retrieval(self):
        async def slow(*_args):
            await asyncio.sleep(1)
        with patch.object(settings, "RESEARCH_DEADLINE_SECONDS", .02), patch.object(orchestrator, "_retrieve_for_query", side_effect=slow):
            before = time.monotonic()
            result = asyncio.run(orchestrator.retrieve_for_query("question", "owner"))
            self.assertEqual(result["availability_notices"], [{"type": "research_timeout"}])
            self.assertLess(time.monotonic() - before, .2)
