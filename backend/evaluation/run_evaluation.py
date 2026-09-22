#!/usr/bin/env python3
"""Small reproducible AskLaw routing, verification, and retrieval evaluation."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.claim_verifier import calculate_grounding_score, verify_claims
from app.services.query_router import route_query


CASES_PATH = Path(__file__).with_name("cases.json")


def load_cases():
    with CASES_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def run_offline(cases):
    results = []

    for case in cases:
        if case["category"] == "verification":
            report = verify_claims(case["answer"], case.get("evidence", []))
            supports = [claim["support"] for claim in report["claims"]]
            expected = case["expected_support"]
            results.append(
                {
                    "id": case["id"],
                    "metric": "claim_support",
                    "expected": expected,
                    "observed": supports,
                    "grounding_score": calculate_grounding_score(report),
                    "support_counts": report["summary"],
                    "pass": bool(supports) and supports[0] == expected,
                }
            )
            continue

        observed = route_query(case["query"]).value
        results.append(
            {
                "id": case["id"],
                "metric": "route",
                "expected": case["expected_route"],
                "observed": observed,
                "pass": observed == case["expected_route"],
            }
        )

    return results


def run_live(cases, user_id, document_id, expected_filename, other_user_id):
    from app.services.retrieval_orchestrator import retrieve_for_query_sync

    results = []

    for case in cases:
        if case["category"] == "verification":
            continue

        scoped_document = document_id if case["category"] in {"document", "hybrid", "isolation"} else None
        scoped_user = other_user_id if case["category"] == "isolation" and other_user_id else user_id
        response = retrieve_for_query_sync(
            query=case["query"],
            user_id=scoped_user,
            document_id=scoped_document,
        )
        rag_results = response.get("rag_results", [])
        web_results = response.get("web_results", [])
        filenames = sorted(
            {
                item.get("filename")
                for item in rag_results
                if item.get("filename")
            }
        )
        isolation_pass = None
        if case["category"] == "isolation" and other_user_id:
            isolation_pass = len(rag_results) == 0

        results.append(
            {
                "id": case["id"],
                "expected_route": case["expected_route"],
                "observed_route": response.get("route"),
                "retrieval_returned": bool(rag_results or web_results),
                "rag_count": len(rag_results),
                "web_count": len(web_results),
                "filenames": filenames,
                "correct_source_returned": (
                    expected_filename in filenames if expected_filename else None
                ),
                "document_isolation_pass": isolation_pass,
            }
        )

    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Run retrieval against local services")
    parser.add_argument("--user-id", help="MongoDB user ID for the live run")
    parser.add_argument("--other-user-id", help="Second user ID for the isolation case")
    parser.add_argument("--document-id", help="Indexed document ID for document cases")
    parser.add_argument("--expected-filename", help="Expected source filename for live document cases")
    args = parser.parse_args()

    cases = load_cases()
    results = run_offline(cases)

    if args.live:
        if not args.user_id or not args.document_id:
            parser.error("--live requires --user-id and --document-id")
        results.extend(
            run_live(
                cases,
                args.user_id,
                args.document_id,
                args.expected_filename,
                args.other_user_id,
            )
        )

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
