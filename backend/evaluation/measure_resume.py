#!/usr/bin/env python3
"""Small opt-in live measurements, not a load test or legal-accuracy evaluator.

Run from backend/. Creates one ordinary expiring guest, never saves conversations,
and sends only checked-in fictional descriptions to the real intake provider.
Secrets, cookies, user IDs, answer bodies and raw provider errors are not saved.
"""
import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
import logging
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time
from unittest.mock import patch
from urllib.parse import urlsplit

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation.run_evaluation import load_cases, run_offline

CASES = Path(__file__).with_name("resume_cases.json")
PUBLIC_API = "https://asklaw-api.onrender.com"
SCORED_FIELDS = {"buyer_name", "seller_name", "product", "order_reference", "amount_inr"}
HARNESS_VERSION = "4"


def failure_diagnostic(exc):
    """Allowlisted categories/status only. Never retain exception messages."""
    chain = []
    current = exc
    while current is not None and len(chain) < 6 and all(current is not item for item in chain):
        chain.append(current)
        current = current.__cause__
    for item in reversed(chain):
        if isinstance(item, (TimeoutError, httpx.TimeoutException)):
            return {"category": "timeout"}
        if isinstance(item, httpx.RemoteProtocolError):
            return {"category": "remote_protocol_error"}
        if isinstance(item, httpx.LocalProtocolError):
            return {"category": "local_protocol_error"}
        if isinstance(item, httpx.NetworkError):
            return {"category": "network_error"}
        code = getattr(item, "status_code", None)
        if code is None and isinstance(item, httpx.HTTPStatusError):
            code = item.response.status_code
        if isinstance(code, int) and not isinstance(code, bool) and 100 <= code <= 599:
            return {"category": "http_status", "http_status": code}
        if isinstance(item, json.JSONDecodeError):
            return {"category": "invalid_json"}
    if isinstance(exc, (ValueError, TypeError, KeyError)):
        return {"category": "invalid_data"}
    return {"category": "unclassified"}


def distribution(values):
    """No fabricated zero for missing measurements or dubious small-sample p95."""
    values = list(values)
    return {"n": len(values), "min_seconds": round(min(values), 3),
            "median_seconds": round(statistics.median(values), 3),
            "max_seconds": round(max(values), 3)} if values else {"n": 0, "min_seconds": None, "median_seconds": None, "max_seconds": None}


def normalized(value):
    return " ".join(str(value).strip().rstrip(".!?").casefold().split())


def score_intake(case, response):
    expected = {(field, normalized(value)) for field, values in case["expected_fields"].items() for value in values}
    observed = {(item["field"], normalized(item["value"])) for item in response.get("suggestions", [])
                if item.get("field") in SCORED_FIELDS}
    suggestions = response.get("suggestions", [])
    dates = [item["event"].get("occurred_on") for item in suggestions if "event" in item and item["event"].get("occurred_on")]
    return {"scope_pass": response.get("supported") == case["supported"],
            "field_true_positive": len(expected & observed), "field_false_positive": len(observed - expected),
            "field_false_negative": len(expected - observed),
            "missing_fields": sorted([list(pair) for pair in expected - observed]),
            "unexpected_fields": sorted([list(pair) for pair in observed - expected]),
            "quote_total": len(suggestions),
            "quote_exact": sum(bool(item.get("quote")) and item["quote"] in case["description"] for item in suggestions),
            "dates_not_invented": all(value in case["allowed_event_dates"] for value in dates)}


def intake_summary(rows):
    successful = [row for row in rows if row["status"] == "ok"]
    tp = sum(row["score"]["field_true_positive"] for row in successful)
    fp = sum(row["score"]["field_false_positive"] for row in successful)
    fn = sum(row["score"]["field_false_negative"] for row in successful)
    # Missing responses remain in the scope denominator, not quietly excluded.
    expected_total = sum(row["expected_fact_count"] for row in rows) if rows and all("expected_fact_count" in row for row in rows) else None
    return {"attempted": len(rows), "responses": len(successful),
            "scope_passes": sum(row["score"]["scope_pass"] for row in successful),
            "scope_denominator": len(rows), "field_true_positive": tp, "field_false_positive": fp,
            "field_false_negative": fn, "field_metrics_response_denominator": len(successful),
            "micro_precision": tp / (tp + fp) if tp + fp else None,
            "micro_recall": tp / (tp + fn) if tp + fn else None,
            "planned_expected_facts": expected_total,
            "end_to_end_expected_fact_recall": tp / expected_total if expected_total else None,
            "response_latency": distribution(row["elapsed_seconds"] for row in successful)}


class StreamObservation:
    def __init__(self):
        self.answer = []
        self.first_answer_seconds = None
        self.sources = []
        self.route = None
        self.grounding_score = None
        self.claim_summary = {}
        self.errors = 0
        self.unavailable = False

    def consume(self, event, elapsed):
        if event.get("type") == "token" and event.get("content"):
            if self.first_answer_seconds is None:
                self.first_answer_seconds = elapsed
            self.answer.append(event["content"])
        elif event.get("type") == "sources":
            self.sources = event.get("sources", [])
        elif event.get("type") == "route":
            self.route = event.get("route")
        elif event.get("type") == "verification":
            self.grounding_score = event.get("grounding_score")
            self.claim_summary = event.get("summary", {})
        elif event.get("type") == "error":
            self.errors += 1
        elif event.get("type") == "availability" and event.get("notices"):
            self.unavailable = True

    def result(self, elapsed, status_code):
        from app.services.prompt_service import insufficient_evidence_message
        answer = "".join(self.answer).strip()
        insufficient = answer.casefold() == insufficient_evidence_message(self.route or "web").casefold()
        terminal_route_received = self.route in ("rag", "web", "hybrid", "conversation")
        success = status_code == 200 and bool(answer) and bool(self.sources) and terminal_route_received and not (self.errors or self.unavailable or insufficient)
        return {"status": "ok" if success else "unavailable" if self.unavailable else "failed",
                "http_status": status_code, "elapsed_seconds": round(elapsed, 6),
                "first_answer_seconds": self.first_answer_seconds,
                "source_count": len(self.sources), "source_domains": sorted({urlsplit(s.get("url", "")).hostname for s in self.sources if urlsplit(s.get("url", "")).hostname}),
                "route": self.route, "answer_characters": len(answer),
                "terminal_route_received": terminal_route_received,
                "answer_sha256": sha256(answer.encode()).hexdigest(), "stream_errors": self.errors,
                "insufficient_evidence": insufficient, "dependency_unavailable": self.unavailable,
                "grounding_score_observation_not_accuracy": self.grounding_score,
                "claim_summary": self.claim_summary}


async def web_request(client, token, case):
    observation = StreamObservation()
    started = time.perf_counter()
    status_code = None
    try:
        async with asyncio.timeout(90):
            async with client.stream("POST", PUBLIC_API + "/chat/stream",
                                     headers={"Authorization": "Bearer " + token},
                                     json={"messages": [{"role": "user", "content": case["query"]}]}) as response:
                status_code = response.status_code
                if response.status_code == 200:
                    async for line in response.aiter_lines():
                        if line.strip():
                            observation.consume(json.loads(line), time.perf_counter() - started)
                row = observation.result(time.perf_counter() - started, response.status_code)
    except (TimeoutError, httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
        row = {**observation.result(time.perf_counter() - started, status_code),
               "status": "request_failed", "failure": failure_diagnostic(exc)}
    return {"id": case["id"], **row}


async def run_web(cases, health_timeout_seconds=65):
    if not isinstance(health_timeout_seconds, int) or not 1 <= health_timeout_seconds <= 120:
        raise ValueError("Health budget must be an integer from 1 to 120 seconds")
    if not 1 <= len(cases) <= 5:
        raise ValueError("One guest, at most five sequential requests; no quota bypass")
    async with httpx.AsyncClient(timeout=httpx.Timeout(90, connect=5), follow_redirects=False) as client:
        started = time.perf_counter()
        try:
            async with asyncio.timeout(health_timeout_seconds):
                health = await client.get(PUBLIC_API + "/health", timeout=httpx.Timeout(health_timeout_seconds, connect=5))
                health.raise_for_status()
            preflight = {"status": "ok", "elapsed_seconds": round(time.perf_counter() - started, 6),
                         "note": "Single preflight observation; prior idle/cold state not controlled"}
            async with asyncio.timeout(30):
                guest = await client.post(PUBLIC_API + "/auth/guest")
                guest.raise_for_status()
                payload = guest.json()
                if payload.get("is_guest") is not True or not isinstance(payload.get("access_token"), str):
                    raise ValueError("Not an ordinary guest response")
                token = payload["access_token"]
        except (TimeoutError, httpx.HTTPError, ValueError, KeyError) as exc:
            return {"preflight": {"status": "setup_failed", "elapsed_seconds": round(time.perf_counter() - started, 6), "failure": failure_diagnostic(exc)},
                    "rows": [{"id": case["id"], "status": "not_run_setup_failed"} for case in cases]}
        rows = []
        for case in cases:
            row = await web_request(client, token, case)
            rows.append(row)
            print(f"live_web id={case['id']} status={row['status']}", flush=True)
            await asyncio.sleep(1)
        # Guest expires normally; no user ID, auth material or conversations saved.
        return {"preflight": preflight, "rows": rows}


async def run_intake(cases):
    from app.services import complaint_intake as service
    rows = []
    for case in cases:
        started = time.perf_counter()
        diagnostic = {}
        original_extract = service._extract

        async def observed_extract(description):
            try:
                return await original_extract(description)
            except Exception as exc:
                diagnostic.update(failure_diagnostic(exc))
                raise

        try:
            # Observe the real extractor without changing its request/retry behavior.
            # Patching is confined to this standalone benchmark process, not the API.
            with patch.object(service, "_extract", new=observed_extract):
                response = await service.prepare_intake(case["description"])
            row = {"id": case["id"], "status": "ok", "elapsed_seconds": round(time.perf_counter() - started, 6),
                   "score": score_intake(case, response)}
        except Exception as exc:
            # Do not store exceptions, provider bodies, URLs or request secrets.
            row = {"id": case["id"], "status": "unavailable", "elapsed_seconds": round(time.perf_counter() - started, 6),
                   "failure": diagnostic or failure_diagnostic(exc)}
        row["expected_fact_count"] = sum(len(values) for values in case["expected_fields"].values())
        rows.append(row)
        print(f"live_intake id={case['id']} status={row['status']}", flush=True)
        await asyncio.sleep(1)
    return rows


def summarize_web(rows):
    successful = [row for row in rows if row["status"] == "ok"]
    return {"planned": len(rows), "completed_with_answer_and_sources": len(successful),
            "status_counts": dict(Counter(row["status"] for row in rows)),
            "successful_first_answer": distribution(row["first_answer_seconds"] for row in successful if row.get("first_answer_seconds") is not None),
            "successful_completion": distribution(row["elapsed_seconds"] for row in successful),
            "all_attempt_completion": distribution(row["elapsed_seconds"] for row in rows if "elapsed_seconds" in row)}


async def measure(live, web_only=False, health_timeout_seconds=65):
    fixture_bytes = CASES.read_bytes()
    cases = json.loads(fixture_bytes)
    offline = run_offline(load_cases())
    report = {"schema_version": 2, "harness_version": HARNESS_VERSION,
              "harness_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
              "legacy_cases_sha256": sha256(Path(__file__).with_name("cases.json").read_bytes()).hexdigest(),
              "started_at_utc": datetime.now(timezone.utc).isoformat(),
              "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
              "harness_uncommitted": bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()),
              "python": platform.python_version(), "cases_sha256": sha256(fixture_bytes).hexdigest(),
              "mode": "live" if live else "offline", "offline_curated_cases": offline,
              "measurement_settings": {"live_section": "web" if web_only else "all",
                                       "health_timeout_seconds": health_timeout_seconds,
                                       "chat_timeout_seconds": 90},
              "limitations": ["Small fixed, developer-authored cases; no held-out legal benchmark or expert correctness review.",
                              "Sequential requests, not throughput, concurrent capacity, availability SLA or a load test.",
                              "Public API timings include client-network and server/provider time, exclude browser rendering and Netlify UI.",
                              "API preflight runs before chat; idle/cold state is not controlled. No cold-start improvement claim.",
                              "Intake timings call the real local service/Groq, not deployed registered-account HTTP/auth/persistence.",
                              "Field scores compare normalized exact values on five named scalar fields, not descriptions, remedies or legal validity.",
                              "Scope denominator includes all planned intake cases; field precision/recall only use successful provider responses.",
                              "Grounding is a deterministic evidence-support observation, never legal accuracy.",
                              "No live private-document RAG, indexing, browser flow, two-user isolation or stress test performed.",
                              "No missing results are removed. Harness does not retry failed cases; app/SDK retry policies remain unchanged.",
                              "Failure diagnostics contain allowlisted category/status only; no error bodies/messages/URLs.",
                              "End-to-end expected-fact recall includes every planned fixture fact, including unavailable calls."]}
    if live:
        from app.core.config import settings
        report["providers"] = {"web_local_setting": settings.WEB_SEARCH_PROVIDER,
                               "public_deployed_commit": "not_exposed_by_health_endpoint",
                               "intake_model": "openai/gpt-oss-120b"}
        report["web"] = await run_web(cases["web_questions"], health_timeout_seconds)
        report["web"]["summary"] = summarize_web(report["web"]["rows"])
        if not web_only:
            rows = await run_intake(cases["intake_cases"])
            report["intake"] = {"rows": rows, "summary": intake_summary(rows)}
    report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="One expiring guest, <=5 public chat requests and 6 real Groq intake calls")
    parser.add_argument("--web-only", action="store_true", help="With --live, skip all intake calls; never retries failed cases")
    parser.add_argument("--health-timeout-seconds", type=int, default=65, help="Health preflight total budget, 1–120; default 65; recorded in report")
    parser.add_argument("--output", type=Path, required=True, help="New JSON report path (never overwrite an earlier run)")
    args = parser.parse_args()
    if args.web_only and not args.live:
        parser.error("--web-only requires --live")
    if not 1 <= args.health_timeout_seconds <= 120:
        parser.error("--health-timeout-seconds must be 1–120")
    if args.output.exists():
        parser.error("Report exists; choose a new path so previous runs remain visible")
    # HTTP transport/library logging must not leak auth, account IDs or payloads.
    logging.disable(logging.CRITICAL)
    report = asyncio.run(measure(args.live, args.web_only, args.health_timeout_seconds))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")
    print(f"Report saved: {args.output}")


if __name__ == "__main__":
    main()
