"""Drive async retrieval incrementally inside the existing sync NDJSON stream."""
import asyncio
from collections import deque
import time

from app.services.research_runtime import progress_context


def retrieval_events(awaitable):
    # No additional worker pool: the existing streaming iterator drives this
    # loop serially, while bounded RAG/readiness pools do blocking work.
    loop = asyncio.new_event_loop()
    codes = deque()
    async def run():
        token = progress_context.set(codes.append)
        try:
            return await awaitable
        finally:
            progress_context.reset(token)
    task = loop.create_task(run())
    last_event = time.monotonic()
    try:
        while not task.done():
            loop.run_until_complete(asyncio.sleep(.05))
            while codes:
                yield {"type": "progress", "code": codes.popleft()}
                last_event = time.monotonic()
            if not task.done() and time.monotonic() - last_event >= 1:
                yield {"type": "progress", "code": "research_pending"}
                last_event = time.monotonic()
        yield {"type": "retrieval_result", "result": task.result()}
    finally:
        if not task.done():
            task.cancel()
        loop.run_until_complete(asyncio.gather(task, return_exceptions=True))
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
