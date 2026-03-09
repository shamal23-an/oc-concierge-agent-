"""Test suite for Brydon's real guest questions.

Tests the live API against commonly asked questions grouped by category.
Shows pass/fail for each question based on whether the response contains
useful information vs "I don't have that information" denials.

Usage:
    uv run python scripts/test_brydon_questions.py                    # test against local
    uv run python scripts/test_brydon_questions.py https://...railway.app --key YOUR_API_KEY
    uv run python scripts/test_brydon_questions.py --category general  # test one category
    uv run python scripts/test_brydon_questions.py --verbose           # show full responses
"""

from __future__ import annotations

import os
import sys
import time

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "http://127.0.0.1:8000"

# Phrases that indicate the bot couldn't answer
DENIAL_PHRASES = [
    "i don't have that information",
    "i do not have that information",
    "don't have specific information",
    "not available in my records",
    "i'm unable to find",
    "no relevant documents found",
    "i couldn't find",
    "i could not find",
    "unfortunately, i don't have",
    "unfortunately, i do not have",
    "i'm not able to provide",
]

# ── Question Bank ──────────────────────────────────────────────────────── #

QUESTIONS: dict[str, list[dict]] = {
    "general_availability": [
        {"q": "Is there a minimum night stay requirement?", "tags": ["booking"]},
        {"q": "Can I check in earlier than 15:00?", "tags": ["booking"]},
        {"q": "Can I check out later than 10:30?", "tags": ["booking"]},
    ],
    "general_rates": [
        {
            "q": "What is the rate per night for the Luxury Suite at La Fontaine?",
            "property": "la_fontaine",
            "tags": ["rates"],
        },
        {
            "q": "What is the rate per night for the Deluxe room at Avondrood?",
            "property": "avondrood",
            "tags": ["rates"],
        },
        {"q": "Is breakfast included in the rate?", "tags": ["rates"]},
        {"q": "What are your payment terms?", "tags": ["payment"]},
        {"q": "What methods of payment are accepted?", "tags": ["payment"]},
        {"q": "What is the refund process for cancellations?", "tags": ["cancellation"]},
        {
            "q": "How can I cancel a booking, and are there any cancellation fees?",
            "tags": ["cancellation"],
        },
    ],
    "general_services": [
        {"q": "Are you able to provide a camp cot for a child?", "tags": ["family"]},
        {"q": "Are children welcome at the property?", "tags": ["family"]},
        {"q": "Is there free Wi-Fi onsite?", "tags": ["amenities"]},
        {"q": "Do you offer free airport shuttles or transfers?", "tags": ["transfers"]},
        {"q": "Are pets allowed?", "tags": ["policy"]},
        {"q": "Is there daily room cleaning?", "tags": ["amenities"]},
    ],
    "franschhoek": [
        {
            "q": "What are the private tours that can be arranged by the hotel in Franschhoek?",
            "tags": ["activities"],
        },
        {
            "q": "Can you provide details on recommended local restaurants in Franschhoek?",
            "tags": ["restaurants"],
        },
        {"q": "What is the nearest golf course to Franschhoek?", "tags": ["activities"]},
        {"q": "Can e-bikes be hired locally in Franschhoek?", "tags": ["activities"]},
        {"q": "Do you offer car service or transfers to Stellenbosch?", "tags": ["transfers"]},
        {"q": "Can you recommend any wine tasting tours in Franschhoek?", "tags": ["activities"]},
        {
            "q": "What are the payment terms at La Fontaine? When is the deposit due?",
            "property": "la_fontaine",
            "tags": ["payment"],
        },
        {
            "q": "Is it possible to arrange a late check-out at Avondrood?",
            "property": "avondrood",
            "tags": ["booking"],
        },
    ],
    "cape_town": [
        {
            "q": "Can a Cape Peninsula Tour be booked from POD Camps Bay?",
            "property": "pod_camps_bay",
            "tags": ["activities"],
        },
        {
            "q": "Are entrance fees included in the tour price at POD Camps Bay?",
            "property": "pod_camps_bay",
            "tags": ["activities"],
        },
        {
            "q": "Can airport transfers be arranged from POD Camps Bay?",
            "property": "pod_camps_bay",
            "tags": ["transfers"],
        },
        {
            "q": "What is the minimum stay requirement at POD Camps Bay over peak periods?",
            "property": "pod_camps_bay",
            "tags": ["booking"],
        },
        {
            "q": "Is it possible to store luggage before check-in at Blackheath Lodge?",
            "property": "blackheath_lodge",
            "tags": ["amenities"],
        },
    ],
    "camp_figtree": [
        {
            "q": "What activities do you offer at Camp Figtree?",
            "property": "camp_figtree",
            "tags": ["activities"],
        },
        {
            "q": "Can you send the recommended directions to Camp Figtree?",
            "property": "camp_figtree",
            "tags": ["directions"],
        },
        {
            "q": "Is an SUV or 4x4 required for the road to Camp Figtree?",
            "property": "camp_figtree",
            "tags": ["directions"],
        },
        {
            "q": "Is Wi-Fi available in the suites at Camp Figtree?",
            "property": "camp_figtree",
            "tags": ["amenities"],
        },
        {
            "q": "What time should we plan to arrive at Camp Figtree?",
            "property": "camp_figtree",
            "tags": ["booking"],
        },
        {
            "q": "Can you arrange an airport transfer to Camp Figtree?",
            "property": "camp_figtree",
            "tags": ["transfers"],
        },
        {
            "q": "Should we book the game drive for morning or afternoon?",
            "property": "camp_figtree",
            "tags": ["activities"],
        },
        {
            "q": "Is dinner an a la carte menu or set meal at Camp Figtree?",
            "property": "camp_figtree",
            "tags": ["restaurant"],
        },
        {
            "q": "What is included in the 2-night package at Camp Figtree?",
            "property": "camp_figtree",
            "tags": ["rates"],
        },
        {
            "q": "What is Camp Figtree's cancellation policy?",
            "property": "camp_figtree",
            "tags": ["cancellation"],
        },
        {
            "q": "Do guests need to present a passport for Addo National Park entry?",
            "property": "camp_figtree",
            "tags": ["activities"],
        },
    ],
    "property_discovery": [
        {"q": "What properties do you have?", "tags": ["general"]},
        {"q": "What properties do you have in Franschhoek?", "tags": ["general"]},
        {"q": "What properties do you have near the beach?", "tags": ["general"]},
        {"q": "Which property is best for a family holiday?", "tags": ["general"]},
        {"q": "I want to book a room", "tags": ["booking"]},
    ],
    "spa_and_dining": [
        {
            "q": "What spa treatments does La Fontaine offer?",
            "property": "la_fontaine",
            "tags": ["spa"],
        },
        {
            "q": "What restaurants do you recommend near Avondrood?",
            "property": "avondrood",
            "tags": ["restaurants"],
        },
        {
            "q": "What is on the dinner menu at Camp Figtree?",
            "property": "camp_figtree",
            "tags": ["restaurant"],
        },
    ],
}


def is_denial(response: str) -> bool:
    """Check if the response is a denial / 'I don't know' answer."""
    lower = response.lower()
    return any(phrase in lower for phrase in DENIAL_PHRASES)


def has_contact_escalation(response: str) -> bool:
    """Check if the response includes contact details for escalation."""
    lower = response.lower()
    return "@" in lower or "phone" in lower or "+27" in lower


def run_tests(
    base_url: str,
    *,
    category: str | None = None,
    verbose: bool = False,
    api_key: str = "",
) -> dict:
    """Run all questions and report results."""
    results = {
        "total": 0,
        "answered": 0,
        "denied": 0,
        "denied_with_contact": 0,
        "errors": 0,
        "by_category": {},
        "failures": [],
    }

    categories = {category: QUESTIONS[category]} if category else QUESTIONS

    for cat_name, questions in categories.items():
        cat_results = {"total": 0, "answered": 0, "denied": 0}
        print(f"\n{'=' * 80}")
        print(f"  {cat_name.upper().replace('_', ' ')}")
        print(f"{'=' * 80}")

        for qdata in questions:
            query = qdata["q"]
            property_id = qdata.get("property")
            cat_results["total"] += 1
            results["total"] += 1

            print(f"\n  Q: {query}")
            start = time.perf_counter()

            try:
                payload: dict = {"message": query}
                if property_id:
                    payload["property_id"] = property_id

                headers = {}
                if api_key:
                    headers["X-API-Key"] = api_key

                r = httpx.post(
                    f"{base_url}/chat",
                    json=payload,
                    headers=headers,
                    timeout=120,
                )
                elapsed = time.perf_counter() - start

                if r.status_code != 200:
                    print(f"  ERROR {r.status_code} ({elapsed:.1f}s)")
                    results["errors"] += 1
                    continue

                data = r.json()
                response = data.get("response", "")
                scope = data.get("scope", "")
                sources = data.get("sources", [])

                denied = is_denial(response)
                has_contact = has_contact_escalation(response)

                if denied:
                    cat_results["denied"] += 1
                    results["denied"] += 1
                    if has_contact:
                        results["denied_with_contact"] += 1
                        status = "PARTIAL"
                        icon = "~"
                    else:
                        status = "DENIED"
                        icon = "X"
                    results["failures"].append(
                        {
                            "category": cat_name,
                            "question": query,
                            "status": status,
                            "response_preview": response[:150],
                        }
                    )
                else:
                    cat_results["answered"] += 1
                    results["answered"] += 1
                    status = "OK"
                    icon = "+"

                print(
                    f"  [{icon}] {status} ({elapsed:.1f}s) scope={scope} " f"sources={len(sources)}"
                )

                if verbose or denied:
                    # Show response preview
                    preview = response[:200].replace("\n", " ")
                    print(f"      {preview}")

            except Exception as e:
                elapsed = time.perf_counter() - start
                print(f"  [!] FAILED ({elapsed:.1f}s): {e}")
                results["errors"] += 1

        results["by_category"][cat_name] = cat_results
        answered = cat_results["answered"]
        total = cat_results["total"]
        pct = (answered / total * 100) if total else 0
        print(f"\n  >> {cat_name}: {answered}/{total} answered ({pct:.0f}%)")

    # ── Final Summary ────────────────────────────────────────────────── #
    print(f"\n\n{'#' * 80}")
    print("  FINAL RESULTS")
    print(f"{'#' * 80}")

    answered = results["answered"]
    denied = results["denied"]
    denied_contact = results["denied_with_contact"]
    errors = results["errors"]
    total = results["total"]
    answer_rate = (answered / total * 100) if total else 0

    print(f"\n  Total questions:     {total}")
    print(f"  Answered:            {answered} ({answer_rate:.0f}%)")
    print(f"  Denied (no info):    {denied - denied_contact}")
    print(f"  Partial (+ contact): {denied_contact}")
    print(f"  Errors:              {errors}")

    print("\n  By Category:")
    for cat, cr in results["by_category"].items():
        pct = (cr["answered"] / cr["total"] * 100) if cr["total"] else 0
        bar = "#" * int(pct / 5) + "." * (20 - int(pct / 5))
        print(f"    {cat:25s} {cr['answered']:2d}/{cr['total']:2d} " f"[{bar}] {pct:.0f}%")

    if results["failures"]:
        print(f"\n  Failed Questions ({len(results['failures'])}):")
        for f in results["failures"]:
            print(f"    [{f['status']:7s}] {f['question']}")
            print(f"             {f['response_preview'][:100]}")

    print()
    return results


def main() -> None:
    base = os.getenv("API_BASE_URL", BASE_URL)
    category = None
    verbose = False
    api_key = os.getenv("API_KEY", "")

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        arg = args[i]
        if arg.startswith("http"):
            base = arg.rstrip("/")
        elif arg == "--verbose":
            verbose = True
        elif arg == "--key" and i + 1 < len(args):
            i += 1
            api_key = args[i]
        elif arg.startswith("--category"):
            if "=" in arg:
                category = arg.split("=", 1)[1]
            elif i + 1 < len(args):
                i += 1
                category = args[i]
        i += 1

    if category and category not in QUESTIONS:
        print(f"Unknown category: {category}")
        print(f"Available: {', '.join(QUESTIONS.keys())}")
        return

    print(f"Target: {base}")
    print(f"Category: {category or 'ALL'}")
    n = sum(len(q) for q in QUESTIONS.values()) if not category else len(QUESTIONS[category])
    print(f"Questions: {n}")

    # Health check
    try:
        r = httpx.get(f"{base}/health", timeout=5)
        health = r.json()
        print(f"Health: {health}")
    except Exception as e:
        print(f"Cannot connect to {base}: {e}")
        return

    run_tests(base, category=category, verbose=verbose, api_key=api_key)


if __name__ == "__main__":
    main()
