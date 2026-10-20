"""Bounded synchronous provider work with cancellable NDJSON progress."""
from email.utils import parsedate_to_datetime
import logging
import math
import queue
import threading
import time

import httpx

logger = logging.getLogger(__name__)


class ProviderTransportLogFilter(logging.Filter):
    def filter(self, record):
        args = record.args
        # HTTPX INFO otherwise prints the provider URL for every attempt.
        return not (isinstance(args, tuple) and len(args) > 1 and getattr(args[1], "host", None) == "api.groq.com")


logging.getLogger("httpx").addFilter(ProviderTransportLogFilter())


class GenerationBusy(RuntimeError):
    pass


class GenerationTimeout(RuntimeError):
    pass


def retry_delay(exc):
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", {})
    for key, scale in (("retry-after-ms", .001), ("retry-after", 1)):
        value = headers.get(key)
        if value is None:
            continue
        try:
            seconds = float(value) * scale
        except (ValueError, TypeError):
            try:
                seconds = parsedate_to_datetime(value).timestamp() - time.time()
            except (ValueError, TypeError, OverflowError):
                continue
        if math.isfinite(seconds) and seconds >= 0:
            return max(1, seconds)
    return 1


class GenerationPool:
    def __init__(self, workers=2):
        self.slots = threading.BoundedSemaphore(workers)

    def events(self, create, *, budget, request_timeout, max_retry_wait, request_id, heartbeat=1):
        if not self.slots.acquire(blocking=False):
            raise GenerationBusy()
        stopped = threading.Event()
        output = queue.Queue(maxsize=32)
        end = time.monotonic() + budget

        def put(value):
            while not stopped.is_set() and time.monotonic() < end:
                try:
                    output.put(value, timeout=min(.05, max(.001, end - time.monotonic())))
                    return
                except queue.Full:
                    pass

        def worker():
            stream = None
            try:
                for attempt in range(2):
                    remaining = end - time.monotonic()
                    if stopped.is_set() or remaining <= 0:
                        return
                    try:
                        timeout = min(request_timeout, remaining)
                        stream = create(httpx.Timeout(timeout, connect=min(5, timeout)))
                        break
                    except Exception as exc:
                        status = getattr(exc, "status_code", None)
                        if status not in (429, 500, 502, 503, 504):
                            raise
                        delay = retry_delay(exc)
                        if attempt or delay > max_retry_wait or delay >= end - time.monotonic():
                            raise GenerationBusy() from None
                        logger.info("generation request_id=%s phase=retry attempt=%d status=%s wait_seconds=%.3f",
                                    request_id, attempt + 1, status, delay)
                        put(("progress", "provider_retrying"))
                        if stopped.wait(delay):
                            return
                if stream is None:
                    raise GenerationTimeout()
                for chunk in stream:
                    if stopped.is_set() or time.monotonic() >= end:
                        return
                    if chunk.choices and chunk.choices[0].delta.content:
                        put(("token", chunk.choices[0].delta.content))
                put(("done", None))
            except Exception as exc:
                # Exception objects stay process-local; never log their text.
                put(("failure", exc))
            finally:
                try:
                    close = getattr(stream, "close", None)
                    if close:
                        close()
                except Exception:
                    logger.warning("generation request_id=%s phase=cleanup status=failed", request_id)
                finally:
                    self.slots.release()

        thread = threading.Thread(target=worker, name="asklaw-generation", daemon=True)
        try:
            thread.start()
        except BaseException:
            self.slots.release()
            raise
        try:
            retrying = False
            while True:
                remaining = end - time.monotonic()
                if remaining <= 0:
                    raise GenerationTimeout()
                try:
                    kind, value = output.get(timeout=min(heartbeat, remaining))
                except queue.Empty:
                    yield {"type": "progress", "code": "provider_retrying" if retrying else "provider_pending"}
                    continue
                if time.monotonic() >= end:
                    raise GenerationTimeout()
                if kind == "done":
                    return
                if kind == "failure":
                    raise value
                if kind == "progress":
                    retrying = True
                    yield {"type": "progress", "code": value}
                else:
                    retrying = False
                    yield {"type": "token", "content": value}
        finally:
            stopped.set()
            # Do not release here: a blocked worker still owns its slot until
            # network/stream cleanup finishes. Late results are discarded.


generation_pool = GenerationPool()
