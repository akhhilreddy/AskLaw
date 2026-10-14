import asyncio
import os
import threading
import time
import unittest
import httpx
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, Mock, patch

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "7")
from app.core.config import settings
from app.services import research_runtime as runtime, retrieval_orchestrator as orchestrator


class ReadinessTests(unittest.TestCase):
    def test_readiness_diagnostics_are_sanitized_with_short_connect_timeout(self):
        state = runtime.SharedWebReadiness()
        client = Mock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        sensitive = "https://private.example/secret?q=private-question"
        client.get = AsyncMock(side_effect=[
            httpx.ReadTimeout(sensitive), Mock(status_code=502),
            httpx.ConnectError(sensitive), Mock(status_code=200),
        ])
        try:
            with patch.object(runtime.httpx, "AsyncClient", return_value=client), patch.object(runtime.asyncio, "sleep", new=AsyncMock()), self.assertLogs(runtime.logger, level="INFO") as logs:
                self.assertTrue(state._probe(sensitive, 40))
            self.assertEqual(client.get.call_count, 4)
            self.assertTrue(all(call.kwargs["timeout"].connect == 5 for call in client.get.call_args_list))
            self.assertTrue(all(35 < call.kwargs["timeout"].read <= 40 for call in client.get.call_args_list))
            for number, status in enumerate(("timeout", "502", "connection_error", "ok"), 1):
                self.assertIn("attempt=%d" % number, logs.output[number - 1])
                self.assertIn("elapsed_seconds=", logs.output[number - 1])
                self.assertIn("status=" + status, logs.output[number - 1])
            self.assertNotIn("private", "\n".join(logs.output))
            self.assertNotIn("https://", "\n".join(logs.output))
        finally:
            state.executor.shutdown(wait=True)

    def test_slow_success_can_use_more_than_old_five_second_attempt_allowance(self):
        state = runtime.SharedWebReadiness()
        clock = [0.0]
        client = Mock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        async def request(*_args, timeout):
            self.assertEqual(timeout.connect, 5)
            self.assertEqual(timeout.read, 50)
            clock[0] += 32.5
            return Mock(status_code=200)
        client.get = AsyncMock(side_effect=request)
        try:
            with patch.object(runtime.httpx, "AsyncClient", return_value=client), patch.object(runtime.time, "monotonic", side_effect=lambda: clock[0]):
                self.assertTrue(state._probe("https://example.test/search", 50))
            self.assertEqual(client.get.call_count, 1)
            self.assertEqual(clock[0], 32.5)
        finally:
            state.executor.shutdown(wait=True)

    def test_attempt_hard_deadline_cancels_request_and_exhausts_budget(self):
        state = runtime.SharedWebReadiness()
        client = Mock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        cancelled = threading.Event()
        async def request(*_args, timeout):
            self.assertLessEqual(timeout.read, .04)
            self.assertLessEqual(timeout.connect, .04)
            try:
                await asyncio.sleep(1)
            finally:
                cancelled.set()
        client.get = AsyncMock(side_effect=request)
        try:
            with patch.object(runtime.httpx, "AsyncClient", return_value=client):
                before = time.monotonic()
                self.assertFalse(state._probe("https://example.test/search", .04))
                self.assertLess(time.monotonic() - before, .2)
            self.assertTrue(cancelled.is_set())
            self.assertEqual(client.get.call_count, 1)
        finally:
            state.executor.shutdown(wait=True)

    def test_retry_attempt_timeout_uses_only_remaining_budget(self):
        state = runtime.SharedWebReadiness()
        clock = [0.0]
        client = Mock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        async def request(*_args, timeout):
            clock[0] += 12 if client.get.await_count == 1 else 20
            return Mock(status_code=502 if client.get.await_count == 1 else 200)
        async def sleep(seconds):
            clock[0] += seconds
        client.get = AsyncMock(side_effect=request)
        try:
            with patch.object(runtime.httpx, "AsyncClient", return_value=client), patch.object(runtime.time, "monotonic", side_effect=lambda: clock[0]), patch.object(runtime.asyncio, "sleep", side_effect=sleep):
                self.assertTrue(state._probe("https://example.test/search", 50))
            self.assertEqual([call.kwargs["timeout"].read for call in client.get.call_args_list], [50, 37])
            self.assertEqual(clock[0], 33)
        finally:
            state.executor.shutdown(wait=True)

    def test_immediate_probe_is_not_duplicated_across_event_loops(self):
        state = runtime.SharedWebReadiness()
        try:
            with patch.object(state, "_probe", return_value=True) as probe, ThreadPoolExecutor(max_workers=8) as callers:
                outcomes = list(callers.map(lambda _: asyncio.run(state.ensure()), range(20)))
            self.assertTrue(all(outcomes))
            self.assertEqual(probe.call_count, 1)
        finally:
            state.executor.shutdown(wait=True)
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
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.get = AsyncMock(side_effect=[Mock(status_code=502), Mock(status_code=502), Mock(status_code=200), Mock(status_code=200)])
        try:
            with patch.object(runtime.httpx, "AsyncClient", return_value=client), patch.object(runtime.asyncio, "sleep", new=AsyncMock()) as sleep:
                self.assertTrue(asyncio.run(state.ensure()))
                self.assertTrue(asyncio.run(state.ensure()))
                state.ready_at = time.monotonic() - settings.SEARXNG_IDLE_REPROBE_SECONDS - 1
                self.assertTrue(asyncio.run(state.ensure()))
            self.assertEqual(client.get.call_count, 4)
            self.assertEqual(sleep.await_count, 2)
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

    def test_rag_fallback_gets_new_readiness_window_without_resetting_overall_cap(self):
        state = runtime.SharedWebReadiness()
        budgets = []
        async def slow_rag(*_args):
            await asyncio.sleep(.06)
            return []
        def probe(_url, budget):
            budgets.append(budget)
            time.sleep(.05)
            return True
        async def web(*_args):
            return ["web evidence"] if await state.ensure() else []
        try:
            with patch.object(settings, "RESEARCH_DEADLINE_SECONDS", .25), patch.object(settings, "SEARXNG_READINESS_BUDGET_SECONDS", .10), patch.object(orchestrator, "route_query", return_value=orchestrator.QueryRoute.RAG), patch.object(runtime.rag_pool, "run", side_effect=slow_rag), patch.object(orchestrator, "retrieve_web", side_effect=web), patch.object(state, "_probe", side_effect=probe):
                result = asyncio.run(orchestrator.retrieve_for_query("question", "owner"))
            self.assertEqual(result["web_results"], ["web evidence"])
            self.assertEqual(result["route"], "web")
            # RAG's 60ms must not be subtracted from the new 100ms window.
            self.assertGreater(budgets[0], .09)
            self.assertLessEqual(budgets[0], .10)
        finally:
            state.executor.shutdown(wait=True)

    def test_rag_fallback_readiness_is_truncated_by_original_overall_deadline(self):
        state = runtime.SharedWebReadiness()
        budgets = []
        async def slow_rag(*_args):
            await asyncio.sleep(.06)
            return []
        def probe(_url, budget):
            budgets.append(budget)
            time.sleep(.01)
            return False
        async def web(*_args):
            await state.ensure()
            return []
        try:
            with patch.object(settings, "RESEARCH_DEADLINE_SECONDS", .10), patch.object(settings, "SEARXNG_READINESS_BUDGET_SECONDS", .10), patch.object(orchestrator, "route_query", return_value=orchestrator.QueryRoute.RAG), patch.object(runtime.rag_pool, "run", side_effect=slow_rag), patch.object(orchestrator, "retrieve_web", side_effect=web), patch.object(state, "_probe", side_effect=probe):
                before = time.monotonic()
                asyncio.run(orchestrator.retrieve_for_query("question", "owner"))
                self.assertLess(time.monotonic() - before, .2)
            self.assertGreater(budgets[0], 0)
            self.assertLessEqual(budgets[0], .04)
        finally:
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
