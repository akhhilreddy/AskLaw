"""One real fictional-source smoke check; no legal accuracy or speed-up claim."""
import argparse
import asyncio
from hashlib import sha256
import json
import logging
from pathlib import Path
import time

import httpx
from groq import AsyncGroq

from app.core.config import settings
from app.services.prompt_service import build_legal_prompt
from app.services.token_budget import request_measurement
from evaluation.measure_prompt_budget import cases
from evaluation.measure_resume import failure_diagnostic


async def check():
    case = cases()[1]  # Frozen five-source fictional fixture, never real legal facts.
    prompt = build_legal_prompt(case["query"], route=case["route"], evidence_bundle={"evidence": case["evidence"]})
    messages = [{"role": "system", "content": prompt}, {"role": "user", "content": case["query"]}]
    report = {"scope": "one fictional-source generation smoke check; not legal quality or production latency",
              "model": "openai/gpt-oss-120b", "max_completion_tokens": 512,
              "prompt_source_sha256": sha256(Path("app/services/prompt_service.py").read_bytes()).hexdigest(),
              "local_budget": request_measurement(messages, completion_tokens=512),
              "automatic_retries": 0}
    started = time.perf_counter()
    try:
        async with asyncio.timeout(30):
            async with AsyncGroq(api_key=settings.GROQ_API_KEY, max_retries=0, timeout=httpx.Timeout(15, connect=5)) as client:
                raw = await client.with_raw_response.chat.completions.create(model=report["model"], messages=messages,
                                                                            temperature=0, max_completion_tokens=512)
                response = await raw.parse()
                answer = response.choices[0].message.content or ""
                usage = response.usage
                report.update({"status": "response_received", "http_status": raw.status_code,
                               "nonempty_answer": bool(answer.strip()), "answer_sha256": sha256(answer.encode()).hexdigest(),
                               "usage": {name: getattr(usage, name, None) for name in ("prompt_tokens", "completion_tokens", "total_tokens")},
                               "lexical_smoke_checks_not_accuracy": {word: word in answer.lower() for word in ("review", "receipt", "disput")}})
    except Exception as exc:
        report.update({"status": "failed", "failure": failure_diagnostic(exc)})
    report["elapsed_seconds"] = round(time.perf_counter() - started, 6)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a fresh report path")
    logging.disable(logging.CRITICAL)
    report = asyncio.run(check())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
