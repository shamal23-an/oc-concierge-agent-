"""Full guest journey evaluation - a realistic 30-message conversation.

Simulates a real guest discovering properties, asking about rates, activities,
making a booking, switching properties, asking irrelevant questions, coming back,
and testing every aspect of the concierge agent.

Usage:
    uv run python scripts/evaluate_full_journey.py
    uv run python scripts/evaluate_full_journey.py --target https://your-railway-url.up.railway.app
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import uuid

import httpx
from dotenv import load_dotenv

load_dotenv()

DEFAULT_TARGET = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
API_KEY = os.getenv("API_KEY", "")

# Colors for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

# The full guest journey - 30 messages covering every scenario
JOURNEY = [
    # ---- Phase 1: Greeting & Discovery ----
    {
        "message": "Hey there!",
        "phase": "GREETING",
        "expect": "greeting response",
        "checks": {
            "contains_any": ["welcome", "hello", "hi", "help"],
        },
    },
    {
        "message": "I'm planning a trip to South Africa with my partner. What do you recommend?",
        "phase": "DISCOVERY",
        "expect": "overview of regions/properties",
        "checks": {
            "contains_any": ["franschhoek", "cape town", "addo", "property", "region"],
            "not_contains": "which property",
        },
    },
    {
        "message": "We love wine and fine dining. Where should we go?",
        "phase": "DISCOVERY",
        "expect": "recommend Franschhoek properties",
        "checks": {
            "contains_any": ["franschhoek", "la fontaine", "wine"],
        },
    },
    # ---- Phase 2: Property Selection & Deep Dive ----
    {
        "message": "La Fontaine sounds amazing. Tell me everything about it.",
        "phase": "PROPERTY",
        "expect": "La Fontaine details",
        "checks": {
            "contains": "la fontaine",
            "scope_is": "property",
            "property_is": "la_fontaine",
        },
    },
    {
        "message": "What room types do they have?",
        "phase": "CONTEXT RETENTION",
        "expect": "La Fontaine rooms (NOT ask which property)",
        "checks": {
            "not_contains": "which property",
            "property_is": "la_fontaine",
            "contains_any": ["room", "suite", "luxury", "deluxe", "standard"],
        },
    },
    {
        "message": "What are the rates?",
        "phase": "CONTEXT RETENTION",
        "expect": "La Fontaine rates",
        "checks": {
            "not_contains": "which property",
            "property_is": "la_fontaine",
            "contains_any": ["rate", "R", "per night", "season", "price"],
        },
    },
    {
        "message": "Do they have a restaurant?",
        "phase": "CONTEXT RETENTION",
        "expect": "La Fontaine restaurant info",
        "checks": {
            "not_contains": "which property",
            "property_is": "la_fontaine",
        },
    },
    {
        "message": "What about spa treatments?",
        "phase": "CONTEXT RETENTION",
        "expect": "La Fontaine spa info or escalation",
        "checks": {
            "not_contains": "which property",
        },
    },
    # ---- Phase 3: Irrelevant / Out-of-Scope Question ----
    {
        "message": "By the way, what's the capital of France?",
        "phase": "OUT OF SCOPE",
        "expect": "politely decline, redirect to hospitality",
        "checks": {
            "not_contains": "Paris",
            "contains_any": [
                "oyster collection",
                "properties",
                "hospitality",
                "help you with",
                "travel",
                "south africa",
            ],
        },
    },
    # ---- Phase 4: Return to Property (context should persist) ----
    {
        "message": "OK sorry, back to La Fontaine. What's the check-in time?",
        "phase": "CONTEXT RETURN",
        "expect": "La Fontaine check-in time",
        "checks": {
            "not_contains": "which property",
            "property_is": "la_fontaine",
            "contains_any": ["14", "check-in", "check in", "2pm", "2 pm"],
        },
    },
    {
        "message": "And check-out?",
        "phase": "CONTEXT RETENTION",
        "expect": "La Fontaine check-out time",
        "checks": {
            "not_contains": "which property",
            "contains_any": ["10", "check-out", "check out"],
        },
    },
    {
        "message": "What's the cancellation policy?",
        "phase": "CONTEXT RETENTION",
        "expect": "cancellation info or escalation to property",
        "checks": {
            "not_contains": "which property",
        },
    },
    # ---- Phase 5: Booking Intent ----
    {
        "message": "I'd like to book the Luxury Suite for 2 guests, April 15-18",
        "phase": "BOOKING",
        "expect": "acknowledge booking details, provide next steps",
        "checks": {
            "not_contains": "which property",
            "contains_any": ["book", "reserv", "april", "luxury", "contact", "email", "confirm"],
        },
    },
    {
        "message": "Is breakfast included?",
        "phase": "BOOKING FOLLOW-UP",
        "expect": "breakfast info for La Fontaine",
        "checks": {
            "not_contains": "which property",
            "contains_any": [
                "breakfast",
                "included",
                "B&B",
                "bed and breakfast",
                "complimentary",
                "meal",
            ],
        },
    },
    {
        "message": "Can I bring my dog?",
        "phase": "POLICY",
        "expect": "pet policy or escalation",
        "checks": {
            "not_contains": "which property",
        },
    },
    # ---- Phase 6: Cross-Property Switch ----
    {
        "message": "Actually, my partner wants to also spend a few nights at the beach. What about POD Camps Bay?",
        "phase": "CONTEXT SWITCH",
        "expect": "POD Camps Bay info",
        "checks": {
            "contains_any": ["pod", "camps bay", "beach", "cape town"],
            "property_is": "pod_camps_bay",
        },
    },
    {
        "message": "What rooms do they have there?",
        "phase": "CONTEXT RETENTION (new property)",
        "expect": "POD rooms (NOT ask which property)",
        "checks": {
            "not_contains": "which property",
            "property_is": "pod_camps_bay",
        },
    },
    {
        "message": "How do the rates compare to La Fontaine?",
        "phase": "CROSS-PROPERTY COMPARISON",
        "expect": "comparison of rates between POD and La Fontaine",
        "checks": {
            "contains_any": ["pod", "camps bay", "la fontaine", "rate", "compare"],
        },
    },
    # ---- Phase 7: Safari Pivot ----
    {
        "message": "We also want to do a safari. What are our options?",
        "phase": "NEW TOPIC",
        "expect": "Camp Figtree / Addo suggestion",
        "checks": {
            "contains_any": ["camp figtree", "addo", "safari", "elephant", "game drive"],
        },
    },
    {
        "message": "Camp Figtree! What activities do they offer?",
        "phase": "PROPERTY SWITCH",
        "expect": "Camp Figtree activities",
        "checks": {
            "property_is": "camp_figtree",
            "contains_any": ["activit", "game drive", "safari", "horse", "elephant", "hike", "spa"],
        },
    },
    {
        "message": "What are the rates for the same?",
        "phase": "ANAPHORIC REFERENCE",
        "expect": "Camp Figtree rates (NOT ask which property)",
        "checks": {
            "not_contains": "which property",
            "property_is": "camp_figtree",
        },
    },
    {
        "message": "How far is it from Port Elizabeth airport?",
        "phase": "CONTEXT RETENTION",
        "expect": "directions from PE to Camp Figtree",
        "checks": {
            "not_contains": "which property",
            "contains_any": [
                "km",
                "hour",
                "drive",
                "direction",
                "route",
                "transfer",
                "airport",
                "gqeberha",
                "n2",
            ],
        },
    },
    # ---- Phase 8: Escalation / Complaint Scenario ----
    {
        "message": "I had a bad experience at one of your properties last year. Who do I complain to?",
        "phase": "ESCALATION",
        "expect": "empathetic response, provide contact details",
        "checks": {
            "contains_any": [
                "sorry",
                "apologize",
                "contact",
                "email",
                "phone",
                "team",
                "management",
                "assist",
            ],
        },
    },
    # ---- Phase 9: Back to Planning (multi-property trip) ----
    {
        "message": "OK thanks. So for our trip, we want 3 nights in Franschhoek at La Fontaine, then 2 nights at POD Camps Bay, then 3 nights at Camp Figtree. Can you help arrange this?",
        "phase": "MULTI-PROPERTY BOOKING",
        "expect": "acknowledge multi-property itinerary",
        "checks": {
            "contains_any": ["la fontaine", "fontaine"],
            "contains_any_2": ["pod", "camps bay"],
            "contains_any_3": ["camp figtree", "figtree"],
        },
    },
    {
        "message": "What would be the total approximate cost for 2 guests?",
        "phase": "COST ESTIMATION",
        "expect": "rate info or escalation for total cost",
        "checks": {
            "contains_any": ["rate", "cost", "price", "R", "contact", "per night", "total"],
        },
    },
    # ---- Phase 10: Random Questions & Edge Cases ----
    {
        "message": "Is there WiFi at all the properties?",
        "phase": "GENERAL AMENITY",
        "expect": "WiFi info or general amenity response",
        "checks": {
            "contains_any": [
                "wifi",
                "wi-fi",
                "internet",
                "connect",
                "available",
                "property",
                "contact",
            ],
        },
    },
    {
        "message": "Do any of your properties have conference facilities?",
        "phase": "GENERAL AMENITY",
        "expect": "conference info or escalation",
        "checks": {},  # open-ended, just check it doesn't crash
    },
    {
        "message": "What payment methods do you accept?",
        "phase": "POLICY",
        "expect": "payment info or escalation",
        "checks": {
            "contains_any": [
                "payment",
                "card",
                "transfer",
                "pay",
                "contact",
                "credit",
                "debit",
                "EFT",
            ],
        },
    },
    {
        "message": "Can you write me a poem about the sunset?",
        "phase": "OUT OF SCOPE",
        "expect": "politely decline",
        "checks": {
            "contains_any": [
                "oyster collection",
                "properties",
                "help",
                "hospitality",
                "travel",
                "south africa",
                "assist",
            ],
        },
    },
    # ---- Phase 11: Final Summary & Goodbye ----
    {
        "message": "Thanks for all the help! Can you summarize our trip plan?",
        "phase": "SUMMARY",
        "expect": "summary mentioning La Fontaine, POD, Camp Figtree",
        "checks": {
            "contains_any": ["la fontaine", "fontaine"],
        },
    },
    {
        "message": "Perfect, goodbye!",
        "phase": "FAREWELL",
        "expect": "warm farewell",
        "checks": {},
    },
]


def run_check(check_type: str, value, response: str, data: dict) -> tuple[bool, str]:
    """Run a single check."""
    resp_lower = response.lower()

    if check_type == "contains":
        passed = value.lower() in resp_lower
        return passed, f"should contain '{value}'"

    if check_type == "not_contains":
        passed = value.lower() not in resp_lower
        return passed, f"should NOT contain '{value}'"

    if check_type.startswith("contains_any"):
        passed = any(k.lower() in resp_lower for k in value)
        return passed, f"should contain one of {value}"

    if check_type == "scope_is":
        actual = data.get("scope", "")
        passed = actual == value
        return passed, f"scope should be '{value}' (got '{actual}')"

    if check_type == "property_is":
        actual = data.get("property_id", "")
        passed = actual == value
        return passed, f"property should be '{value}' (got '{actual or 'None'}')"

    return True, ""


def main():
    parser = argparse.ArgumentParser(description="Full guest journey evaluation")
    parser.add_argument(
        "--target",
        default=DEFAULT_TARGET,
        help=f"API base URL (default: {DEFAULT_TARGET})",
    )
    args = parser.parse_args()
    base_url = args.target.rstrip("/")

    # Health check
    try:
        resp = httpx.get(f"{base_url}/health", timeout=5)
        health = resp.json()
        if health.get("status") != "healthy":
            print(f"{RED}API not healthy: {health}{RESET}")
            sys.exit(1)
    except Exception as e:
        print(f"{RED}Cannot reach API at {base_url}: {e}{RESET}")
        sys.exit(1)

    session_id = f"journey_{uuid.uuid4().hex[:12]}"
    headers = {"X-API-Key": API_KEY} if API_KEY else {}

    print(f"\n{BOLD}{'=' * 80}{RESET}")
    print(f"{BOLD}  FULL GUEST JOURNEY - 30 Message Conversation{RESET}")
    print(f"{BOLD}  Target: {base_url}{RESET}")
    print(f"{BOLD}  Session: {session_id}{RESET}")
    print(f"{BOLD}{'=' * 80}{RESET}")

    total_checks = 0
    passed_checks = 0
    failed_checks = 0
    total_time = 0
    failed_turns = []
    current_phase = ""

    client = httpx.Client()

    for i, turn in enumerate(JOURNEY):
        turn_num = i + 1
        message = turn["message"]
        phase = turn["phase"]
        checks = turn.get("checks", {})

        # Phase header
        if phase != current_phase:
            current_phase = phase
            print(f"\n{CYAN}{BOLD}  --- {phase} ---{RESET}")

        # Send message
        t0 = time.perf_counter()
        try:
            resp = client.post(
                f"{base_url}/chat",
                json={"message": message, "session_id": session_id},
                headers=headers,
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            elapsed = time.perf_counter() - t0
            print(f"\n  {RED}T{turn_num:02d} ERROR ({elapsed:.1f}s): {e}{RESET}")
            failed_checks += len(checks)
            total_checks += len(checks)
            continue

        elapsed = time.perf_counter() - t0
        total_time += elapsed
        response = data.get("response", "")
        scope = data.get("scope", "")
        prop_id = data.get("property_id", "")
        session_id = data.get("session_id", session_id)

        # Run checks
        turn_fails = []
        for check_type, check_value in checks.items():
            total_checks += 1
            passed, reason = run_check(check_type, check_value, response, data)
            if passed:
                passed_checks += 1
            else:
                failed_checks += 1
                turn_fails.append(reason)

        # Status
        if turn_fails:
            marker = f"{RED}FAIL{RESET}"
            failed_turns.append((turn_num, phase, turn_fails))
        else:
            marker = f"{GREEN}OK{RESET}"

        scope_str = f"{DIM}[{scope or '?':8s}]{RESET}"
        prop_str = f"{DIM}[{prop_id or '-':18s}]{RESET}"

        # Print turn
        print(f"\n  {marker}  T{turn_num:02d} ({elapsed:.1f}s) " f"{scope_str} {prop_str}")
        print(f"  {BOLD}Guest:{RESET} {message}")

        # Format response nicely (wrap at ~90 chars, indent)
        resp_clean = response.replace("\n", " ").replace("  ", " ")
        # Show first 300 chars
        if len(resp_clean) > 300:
            resp_clean = resp_clean[:297] + "..."
        print(f"  {DIM}Agent:{RESET} {resp_clean}")

        # Show failures
        for fail in turn_fails:
            print(f"  {RED}  >> FAIL: {fail}{RESET}")

    client.close()

    # ---- Summary ----
    pct = round(100 * passed_checks / total_checks) if total_checks else 100

    print(f"\n{BOLD}{'=' * 80}{RESET}")
    print(f"{BOLD}  RESULTS{RESET}")
    print(f"{'=' * 80}")
    print(f"  Messages:  {len(JOURNEY)}")
    print(f"  Checks:    {passed_checks}/{total_checks} passed ({pct}%)")
    print(f"  Time:      {total_time:.1f}s total, " f"{total_time/len(JOURNEY):.1f}s avg per turn")

    if failed_turns:
        print(f"\n  {RED}{BOLD}FAILURES:{RESET}")
        for turn_num, phase, fails in failed_turns:
            print(f"    T{turn_num:02d} [{phase}]:")
            for f in fails:
                print(f"      - {f}")
    else:
        print(f"\n  {GREEN}{BOLD}ALL CHECKS PASSED!{RESET}")

    print(f"{'=' * 80}\n")

    sys.exit(1 if failed_turns else 0)


if __name__ == "__main__":
    main()
