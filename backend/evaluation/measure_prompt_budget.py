"""Offline paired-fixture prompt measurements; no model, web, guest or database calls."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from app.services.prompt_service import build_legal_prompt
from app.services.token_budget import request_measurement, VOCAB_SHA256


def cases():
    # Fictional source passages only; not statements of actual law.
    text = "Fictional test provision: return the item only after review; keep the receipt. An exception applies when the owner disputes the record. "
    def item(index, kind):
        return {"evidence_id": f"{kind}-{index}", "source_kind": kind,
                "source_type": "rag" if kind == "rag" else "primary", "title": f"Fictional source {index}",
                "url": f"https://example.invalid/source-{index}", "text": text * 8,
                "date_metadata": {"date": "2026-01-01", "source": "publication", "confidence": "medium"},
                "authority_score": 1.0, "freshness_score": .5, "legal_event_score": .2}
    return [{"id": "rag-one", "route": "rag", "query": "What does this document require?", "evidence": [item(1, "rag")]},
            {"id": "web-five", "route": "web", "query": "Explain the fictional provision and its exception.", "evidence": [item(i, "web") for i in range(1, 6)]},
            {"id": "hybrid-five", "route": "hybrid", "query": "Compare the fictional document with the web material.", "evidence": [item(1, "rag"), item(2, "rag"), item(3, "web"), item(4, "web"), item(5, "web")]}]


def compare(report, baseline):
    if report["cases_sha256"] != baseline["cases_sha256"] or report["vocabulary_sha256"] != baseline["vocabulary_sha256"]:
        raise ValueError("Cannot compare different fixtures or vocabularies")
    if [row["id"] for row in report["rows"]] != [row["id"] for row in baseline["rows"]]:
        raise ValueError("Cannot drop or reorder comparison cases")
    result = []
    for current, previous in zip(report["rows"], baseline["rows"]):
        if current["evidence_text_sha256"] != previous["evidence_text_sha256"]:
            raise ValueError("Evidence text changed")
        old, new = previous["input_text_tokens"], current["input_text_tokens"]
        result.append({"id": current["id"], "before_input_text_tokens": old, "after_input_text_tokens": new,
                       "input_text_reduction_percent": round(100 * (old - new) / old, 3),
                       "before_request_budget_tokens": previous["request_budget_tokens"],
                       "after_request_budget_tokens": current["request_budget_tokens"], "evidence_text_unchanged": True})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, help="Optional prior report with identical fixtures/vocabulary")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a fresh output path")
    fixtures = cases()
    report = {"scope": "offline synthetic prompt inputs, not legal quality or production latency",
              "cases_sha256": sha256(json.dumps(fixtures, sort_keys=True).encode()).hexdigest(),
              "vocabulary_sha256": VOCAB_SHA256,
              "prompt_source_sha256": sha256(Path("app/services/prompt_service.py").read_bytes()).hexdigest(),
              "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(), "rows": []}
    for case in fixtures:
        prompt = build_legal_prompt(case["query"], route=case["route"], evidence_bundle={"evidence": case["evidence"]})
        messages = [{"role": "system", "content": prompt}, {"role": "user", "content": case["query"]}]
        report["rows"].append({"id": case["id"], "prompt_characters": len(prompt),
                               "evidence_text_sha256": sha256("\n".join(item["text"] for item in case["evidence"]).encode()).hexdigest(),
                               **request_measurement(messages)})
    if args.baseline:
        raw = args.baseline.read_bytes()
        report["baseline_sha256"] = sha256(raw).hexdigest()
        report["comparison"] = compare(report, json.loads(raw))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
    print(json.dumps(report["rows"], indent=2))


if __name__ == "__main__":
    main()
