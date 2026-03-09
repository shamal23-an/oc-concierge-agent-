"""Evaluation runner — measures RAG accuracy against golden test set."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

load_dotenv()

DEFAULT_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
DEFAULT_API_KEY = os.getenv("API_KEY", "")
GOLDEN_SET_PATH = (
    Path(__file__).resolve().parent.parent / "tests" / "evaluation" / "golden_set.json"
)


def load_golden_set(path: Path) -> list[dict]:
    with open(path) as f:
        data = json.load(f)
    return data["questions"]


def query_api(base_url: str, api_key: str, question: str, property_id: str | None) -> dict:
    """Send a question to the chat API and return response + timing."""
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key

    body = {"message": question}
    if property_id:
        body["property_id"] = property_id

    start = time.perf_counter()
    try:
        resp = httpx.post(
            f"{base_url}/chat",
            json=body,
            headers=headers,
            timeout=30,
        )
        latency = time.perf_counter() - start
        if resp.status_code == 200:
            data = resp.json()
            return {
                "response": data.get("response", ""),
                "sources": data.get("sources", []),
                "scope": data.get("scope"),
                "cached": data.get("cached", False),
                "latency": round(latency, 2),
                "status": "ok",
            }
        return {
            "response": "",
            "sources": [],
            "scope": None,
            "cached": False,
            "latency": round(latency, 2),
            "status": f"error_{resp.status_code}",
        }
    except Exception as e:
        latency = time.perf_counter() - start
        return {
            "response": "",
            "sources": [],
            "scope": None,
            "cached": False,
            "latency": round(latency, 2),
            "status": f"exception: {e}",
        }


def evaluate_response(question: dict, result: dict) -> dict:
    """Evaluate a single response against expected criteria."""
    response_lower = result["response"].lower()
    verdict = {
        "id": question["id"],
        "category": question["category"],
        "question": question["question"],
        "response_preview": result["response"][:200],
        "latency": result["latency"],
        "status": result["status"],
        "checks": {},
    }

    # Check expected_contains
    contains_pass = True
    for term in question.get("expected_contains", []):
        found = term.lower() in response_lower
        verdict["checks"][f"contains:{term}"] = found
        if not found:
            contains_pass = False

    # Check expected_not_contains
    not_contains_pass = True
    for term in question.get("expected_not_contains", []):
        found = term.lower() in response_lower
        verdict["checks"][f"not_contains:{term}"] = not found
        if found:
            not_contains_pass = False

    # Check if response is a denial (no useful info)
    denial_phrases = [
        "i don't have",
        "i do not have",
        "don't have specific",
        "unable to find",
        "no information",
        "i'm not sure",
        "i am not sure",
    ]
    is_denial = any(p in response_lower for p in denial_phrases)

    # Check if response includes escalation contact
    has_escalation = any(x in response_lower for x in ["email", "phone", "@", "+27", "contact"])

    # Overall verdict
    if result["status"] != "ok":
        verdict["result"] = "ERROR"
    elif is_denial and not has_escalation:
        verdict["result"] = "DENIED"
    elif is_denial and has_escalation:
        verdict["result"] = "PARTIAL"
    elif contains_pass and not_contains_pass:
        verdict["result"] = "PASS"
    else:
        verdict["result"] = "FAIL"

    verdict["is_denial"] = is_denial
    verdict["has_escalation"] = has_escalation

    return verdict


def run_evaluation(
    base_url: str,
    api_key: str,
    golden_set_path: Path,
    category_filter: str | None = None,
) -> dict:
    """Run full evaluation and return summary."""
    questions = load_golden_set(golden_set_path)

    if category_filter:
        questions = [q for q in questions if q["category"] == category_filter]

    print(f"Evaluating {len(questions)} questions against {base_url}")
    print("=" * 70)

    results = []
    for i, q in enumerate(questions, 1):
        api_result = query_api(base_url, api_key, q["question"], q.get("property_id"))
        verdict = evaluate_response(q, api_result)
        results.append(verdict)

        icon = {"PASS": "+", "FAIL": "X", "PARTIAL": "~", "DENIED": "-", "ERROR": "!"}
        print(
            f"  [{icon.get(verdict['result'], '?')}] {verdict['id']:20s} "
            f"{verdict['result']:8s} {verdict['latency']:5.1f}s  "
            f"{q['question'][:50]}"
        )

    # Summary
    total = len(results)
    by_result = {}
    by_category: dict[str, dict[str, int]] = {}

    for r in results:
        by_result[r["result"]] = by_result.get(r["result"], 0) + 1
        cat = r["category"]
        if cat not in by_category:
            by_category[cat] = {}
        by_category[cat][r["result"]] = by_category[cat].get(r["result"], 0) + 1

    pass_count = by_result.get("PASS", 0)
    partial_count = by_result.get("PARTIAL", 0)
    accuracy = pass_count / total * 100 if total else 0
    with_escalation = (pass_count + partial_count) / total * 100 if total else 0
    avg_latency = sum(r["latency"] for r in results) / total if total else 0

    print("\n" + "=" * 70)
    print(f"OVERALL: {pass_count}/{total} PASS ({accuracy:.0f}%)")
    print(f"WITH ESCALATION: {pass_count + partial_count}/{total} ({with_escalation:.0f}%)")
    print(f"AVG LATENCY: {avg_latency:.1f}s")
    print(f"\nBREAKDOWN: {by_result}")

    print("\nPER CATEGORY:")
    for cat, counts in sorted(by_category.items()):
        cat_total = sum(counts.values())
        cat_pass = counts.get("PASS", 0)
        cat_pct = cat_pass / cat_total * 100 if cat_total else 0
        print(f"  {cat:20s}: {cat_pass}/{cat_total} ({cat_pct:.0f}%) {counts}")

    summary = {
        "total": total,
        "pass": pass_count,
        "partial": partial_count,
        "denied": by_result.get("DENIED", 0),
        "fail": by_result.get("FAIL", 0),
        "error": by_result.get("ERROR", 0),
        "accuracy_pct": round(accuracy, 1),
        "with_escalation_pct": round(with_escalation, 1),
        "avg_latency": round(avg_latency, 2),
        "by_category": by_category,
        "details": results,
    }

    return summary


def main():
    parser = argparse.ArgumentParser(description="Evaluate RAG accuracy")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API base URL")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, help="API key")
    parser.add_argument("--golden-set", type=Path, default=GOLDEN_SET_PATH)
    parser.add_argument("--category", help="Filter by category")
    parser.add_argument("--output", type=Path, help="Save JSON results to file")
    args = parser.parse_args()

    summary = run_evaluation(args.base_url, args.api_key, args.golden_set, args.category)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(summary, f, indent=2)
        print(f"\nResults saved to {args.output}")


if __name__ == "__main__":
    main()
