"""Post-deployment web-only benchmark with safe stream diagnostics attached."""
import argparse
import asyncio
from collections import Counter
from hashlib import sha256
import json
import logging
from pathlib import Path
from unittest.mock import patch

from evaluation import diagnose_stream, measure_resume


class ObservedStream(measure_resume.StreamObservation):
    def __init__(self):
        super().__init__()
        self.progress_codes = Counter()
        self.error_codes = Counter()

    def consume(self, event, elapsed):
        if event.get("type") == "progress" and event.get("code") in (
            "provider_pending", "provider_retrying", "research_pending", "web_waking", "web_ready", "web_unavailable",
        ):
            self.progress_codes[event["code"]] += 1
        if event.get("type") == "error" and event.get("code") in (
            "generation_busy", "generation_timeout", "generation_interrupted", "generation_unavailable",
        ):
            self.error_codes[event["code"]] += 1
        super().consume(event, elapsed)

    def result(self, elapsed, status_code):
        return {**super().result(elapsed, status_code), "progress_codes": dict(self.progress_codes),
                "error_codes": dict(self.error_codes)}


async def measure():
    # Observe real events; keep cases, guest/quota, pacing and completion checks.
    with patch.object(measure_resume, "web_request", diagnose_stream.observe), patch.object(diagnose_stream, "StreamObservation", ObservedStream):
        report = await measure_resume.measure(True, web_only=True, health_timeout_seconds=100)
    report["instrumentation"] = {
        "entrypoint": "evaluation/measure_postdeploy.py",
        "entrypoint_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "diagnostic_sha256": sha256(Path(diagnose_stream.__file__).read_bytes()).hexdigest(),
        "method": "same five web cases and one guest; diagnostic observer adds allowlisted event counts, request IDs and timings",
        "deployed_revision": "maintainer reports deployment complete; exact commit not exposed by health",
    }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True, help="One guest, five sequential real web requests; consumes allowance")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new path; never replace earlier evidence")
    logging.disable(logging.CRITICAL)
    report = asyncio.run(measure())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
        handle.write("\n")
    print(f"Post-deployment report saved: {args.output}")


if __name__ == "__main__":
    main()
