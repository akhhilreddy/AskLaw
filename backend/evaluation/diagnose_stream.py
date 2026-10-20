"""One opt-in stream diagnostic, not a replacement benchmark or a load test."""
import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import json
import logging
import re
from pathlib import Path
import sys
import time

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation.measure_resume import PUBLIC_API, StreamObservation, failure_diagnostic


async def observe(client, token, case):
    observation = StreamObservation()
    started = time.perf_counter()
    counts = Counter()
    allowed = {"token", "progress", "sources", "verification", "availability", "route", "error"}
    timing = {"headers_seconds": None, "first_event_seconds": None, "last_event_seconds": None,
              "max_event_gap_seconds": 0, "http_version": None}
    previous = 0
    status = None
    stage = "response_headers"
    try:
        async with asyncio.timeout(90):
            async with client.stream("POST", PUBLIC_API + "/chat/stream",
                                     headers={"Authorization": "Bearer " + token},
                                     json={"messages": [{"role": "user", "content": case["query"]}]}) as response:
                status = response.status_code
                correlation = getattr(response, "headers", {}).get("x-request-id", "")
                if re.fullmatch(r"[0-9a-f]{32}", correlation):
                    timing["request_id"] = correlation
                timing["headers_seconds"] = round(time.perf_counter() - started, 6)
                timing["http_version"] = response.http_version if response.http_version in {"HTTP/1.0", "HTTP/1.1", "HTTP/2"} else "other"
                response.raise_for_status()
                stage = "stream_body"
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    event = json.loads(line)
                    elapsed = time.perf_counter() - started
                    timing["first_event_seconds"] = timing["first_event_seconds"] if timing["first_event_seconds"] is not None else round(elapsed, 6)
                    timing["last_event_seconds"] = round(elapsed, 6)
                    timing["max_event_gap_seconds"] = round(max(timing["max_event_gap_seconds"], elapsed - previous), 6)
                    previous = elapsed
                    kind = event.get("type")
                    counts[kind if isinstance(kind, str) and kind in allowed else "other"] += 1
                    observation.consume(event, elapsed)
                stage = "closed"
        result = observation.result(time.perf_counter() - started, status)
    except (TimeoutError, httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
        result = {**observation.result(time.perf_counter() - started, status),
                  "status": "request_failed", "failure": failure_diagnostic(exc)}
        # Only fixed class names, never arbitrary subclass names or exception text.
        result["transport_kind"] = next((name for cls, name in (
            (httpx.ReadError, "read_error"), (httpx.WriteError, "write_error"),
            (httpx.ConnectError, "connect_error"), (httpx.RemoteProtocolError, "remote_protocol_error"),
            (httpx.TimeoutException, "http_timeout"), (TimeoutError, "overall_timeout")) if isinstance(exc, cls)), "other")
    return {"id": case["id"], **result, "stage": stage, "event_counts": dict(counts), **timing}


async def diagnose():
    report = {"purpose": "single diagnostic reproduction; not a benchmark replacement",
              "started_at_utc": datetime.now(timezone.utc).isoformat(),
              "settings": {"health_timeout_seconds": 100, "stream_timeout_seconds": 90, "http2": False}}
    async with httpx.AsyncClient(timeout=httpx.Timeout(100, connect=5), follow_redirects=False, http2=False) as client:
        stage = "health"
        try:
            async with asyncio.timeout(100):
                response = await client.get(PUBLIC_API + "/health")
                response.raise_for_status()
            stage = "guest_creation"
            async with asyncio.timeout(30):
                response = await client.post(PUBLIC_API + "/auth/guest")
                response.raise_for_status()
                payload = response.json()
                if payload.get("is_guest") is not True or not isinstance(payload.get("access_token"), str):
                    raise ValueError("Invalid guest response")
            report["stream"] = await observe(client, payload["access_token"], {
                "id": "complaint-status", "query": "How can I check a consumer complaint status in India?"})
        except (TimeoutError, httpx.HTTPError, ValueError, KeyError) as exc:
            report["setup"] = {"status": "failed", "stage": stage, "failure": failure_diagnostic(exc)}
    report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True, help="One guest, one question, no retries, consumes provider allowance")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new report path; never overwrite evidence")
    logging.disable(logging.CRITICAL)
    report = asyncio.run(diagnose())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
        handle.write("\n")
    print(f"Diagnostic saved: {args.output}")


if __name__ == "__main__":
    main()
