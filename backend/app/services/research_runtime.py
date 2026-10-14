"""Cross-event-loop readiness, bounded RAG workers and retrieval budgets."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
import threading
import time
import logging
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.core.config import settings


class RedactSearchTransportLogs(logging.Filter):
    def filter(self, record):
        # HTTPX's INFO records otherwise include the provider URL/query string.
        args = record.args
        if isinstance(args, tuple) and len(args) > 1:
            host = getattr(args[1], "host", None)
            if host and host == urlsplit(settings.SEARXNG_URL).hostname:
                return False
        return True


logging.getLogger("httpx").addFilter(RedactSearchTransportLogs())

deadline_context = ContextVar("research_deadline", default=None)
progress_context = ContextVar("research_progress", default=None)


def remaining_seconds():
    deadline = deadline_context.get()
    return max(0, deadline - time.monotonic()) if deadline is not None else settings.RESEARCH_DEADLINE_SECONDS


def progress(code):
    callback = progress_context.get()
    if callback:
        callback(code)


class RagUnavailable(RuntimeError):
    pass


class BoundedRagPool:
    def __init__(self, workers=2):
        self.executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="asklaw-rag")
        self.slots = threading.BoundedSemaphore(workers)

    async def run(self, function, *args):
        if not self.slots.acquire(blocking=False):
            raise RagUnavailable("Document research workers are busy")
        try:
            future = self.executor.submit(function, *args)
        except BaseException:
            self.slots.release()
            raise
        # A cancelled await must not release a RUNNING thread's slot early.
        future.add_done_callback(lambda _future: self.slots.release())
        return await asyncio.wait_for(asyncio.wrap_future(future), timeout=remaining_seconds())


rag_pool = BoundedRagPool()


class SharedWebReadiness:
    def __init__(self):
        self.lock = threading.Lock()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="asklaw-web-ready")
        self.future = None
        self.ready_at = None
        self.url = None
        self.result = False

    def _probe(self, url, budget):
        end = time.monotonic() + budget
        parts = urlsplit(url)
        health_url = urlunsplit((parts.scheme, parts.netloc, "/healthz", "", ""))
        # Sync worker is shared across callers/event loops, not asyncio locks.
        with httpx.Client(follow_redirects=False) as client:
            while time.monotonic() < end:
                try:
                    response = client.get(health_url, timeout=min(5, max(.001, end - time.monotonic())))
                    if response.status_code == 200 and time.monotonic() < end:
                        return True
                except (httpx.HTTPError, ValueError):
                    pass
                wait = min(1, max(0, end - time.monotonic()))
                if wait:
                    time.sleep(wait)
        return False

    def _probe_and_record(self, url, budget):
        try:
            result = bool(self._probe(url, budget))
        except Exception:
            result = False
        with self.lock:
            # Record BEFORE the Future becomes done, so an immediate probe
            # cannot race another event loop into launching a duplicate.
            self.result = result
            self.ready_at = time.monotonic() if result else None
            self.url = url
        return result

    def record_success(self, url):
        with self.lock:
            if self.result and self.url == url:
                self.ready_at = time.monotonic()

    def invalidate(self, url):
        with self.lock:
            if self.url == url:
                self.result = False
                self.ready_at = None

    async def ensure(self):
        url = settings.SEARXNG_URL
        budget = min(settings.SEARXNG_READINESS_BUDGET_SECONDS, remaining_seconds())
        waiter_end = time.monotonic() + budget
        with self.lock:
            if self.result and self.url == url and self.ready_at is not None and time.monotonic() - self.ready_at < settings.SEARXNG_IDLE_REPROBE_SECONDS:
                return True
            if self.future is None or self.future.done():
                self.future = self.executor.submit(self._probe_and_record, url, budget)
            future = self.future
        wrapped = asyncio.wrap_future(future)
        try:
            await asyncio.wait_for(asyncio.shield(wrapped), timeout=min(.25, budget))
        except asyncio.TimeoutError:
            progress("web_waking")
        try:
            result = await asyncio.wait_for(asyncio.shield(wrapped), timeout=max(.001, min(waiter_end - time.monotonic(), remaining_seconds())))
            progress("web_ready" if result else "web_unavailable")
            return bool(result)
        except Exception:
            progress("web_unavailable")
            return False


web_readiness = SharedWebReadiness()


async def ensure_web_ready():
    return await web_readiness.ensure()
