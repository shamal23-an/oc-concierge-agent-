"""Conversation continuity evaluation — multi-turn sessions that test context retention.

Tests whether the agent maintains property context, remembers prior info,
and resolves anaphoric references ("the same", "there", "that one") across turns.

Usage:
    uv run python scripts/evaluate_conversations.py
    uv run python scripts/evaluate_conversations.py --target https://your-railway-url.up.railway.app
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

# ── Conversation definitions ─────────────────────────────────────────────── #
# Each conversation is a list of turns. Each turn has:
#   - message: what the user says
#   - checks: list of assertion functions (response, turn_data) -> (pass, reason)
#   - description: what this turn tests

CONVERSATIONS = [
    # ── Conversation 1: Property discovery -> selection -> follow-up rates ──
    {
        "id": "CONV1",
        "name": "Property Discovery to Rates (Franschhoek -> Pink Door)",
        "turns": [
            {
                "message": "Hi there",
                "description": "Greeting",
                "checks": [
                    ("contains", "welcome", "Should greet warmly"),
                ],
            },
            {
                "message": "I'm looking for a place in the wine country",
                "description": "Region query (Franschhoek)",
                "checks": [
                    (
                        "contains_any",
                        ["franschhoek", "la fontaine", "avondrood", "pink door"],
                        "Should mention Franschhoek properties",
                    ),
                ],
            },
            {
                "message": "Tell me more about The Pink Door",
                "description": "Narrow to specific property",
                "checks": [
                    ("contains", "pink door", "Should discuss Pink Door"),
                    ("not_contains", "which property", "Should NOT ask which property"),
                ],
            },
            {
                "message": "What are the rates?",
                "description": "Follow-up rate query (should stay on Pink Door)",
                "checks": [
                    ("not_contains", "which property", "Should NOT ask which property"),
                    ("scope_is", "property", "Scope should be PROPERTY"),
                ],
            },
            {
                "message": "What about room types there?",
                "description": "Anaphoric 'there' should resolve to Pink Door",
                "checks": [
                    ("not_contains", "which property", "Should NOT ask which property"),
                    (
                        "contains_any",
                        ["pink door", "room", "suite", "villa", "bedroom"],
                        "Should discuss Pink Door rooms",
                    ),
                ],
            },
            {
                "message": "Do they have a pool?",
                "description": "'they' should resolve to Pink Door",
                "checks": [
                    ("not_contains", "which property", "Should NOT ask which property"),
                ],
            },
            {
                "message": "What about check-in and check-out times?",
                "description": "Policy follow-up (still Pink Door)",
                "checks": [
                    ("not_contains", "which property", "Should NOT ask which property"),
                ],
            },
            {
                "message": "And the cancellation policy?",
                "description": "'And' implies same property continuation",
                "checks": [
                    ("not_contains", "which property", "Should NOT ask which property"),
                ],
            },
            {
                "message": "Can you give me a summary of everything we discussed?",
                "description": "Summary request — should reference Pink Door",
                "checks": [
                    ("contains", "pink door", "Summary should mention Pink Door"),
                ],
            },
            {
                "message": "Actually, how does La Fontaine compare?",
                "description": "Context switch to comparison",
                "checks": [
                    ("contains_any", ["la fontaine", "fontaine"], "Should discuss La Fontaine"),
                ],
            },
        ],
    },
    # ── Conversation 2: Safari property -> booking flow -> context retention ──
    {
        "id": "CONV2",
        "name": "Safari Booking Flow (Addo -> Camp Figtree)",
        "turns": [
            {
                "message": "Hello! I want to go on safari",
                "description": "Safari intent -> should suggest Addo/Camp Figtree",
                "checks": [
                    (
                        "contains_any",
                        ["camp figtree", "addo", "safari"],
                        "Should mention safari options",
                    ),
                ],
            },
            {
                "message": "Camp Figtree sounds perfect",
                "description": "Selection confirmation",
                "checks": [
                    ("contains", "camp figtree", "Should discuss Camp Figtree"),
                    ("not_contains", "which property", "Should NOT ask which property"),
                ],
            },
            {
                "message": "What activities do they offer?",
                "description": "'they' = Camp Figtree",
                "checks": [
                    ("not_contains", "which property", "Should NOT ask which property"),
                    (
                        "contains_any",
                        ["activit", "game drive", "safari", "elephant", "hike", "horse", "spa"],
                        "Should list Camp Figtree activities",
                    ),
                ],
            },
            {
                "message": "What are the rates for the same?",
                "description": "'the same' = Camp Figtree (THE critical test)",
                "checks": [
                    ("not_contains", "which property", "Should NOT ask which property"),
                    ("scope_is", "property", "Scope should be PROPERTY"),
                    ("property_is", "camp_figtree", "Property should be camp_figtree"),
                ],
            },
            {
                "message": "How do I get there from Port Elizabeth?",
                "description": "'there' = Camp Figtree",
                "checks": [
                    ("not_contains", "which property", "Should NOT ask which property"),
                    (
                        "contains_any",
                        [
                            "direction",
                            "drive",
                            "km",
                            "hour",
                            "route",
                            "port elizabeth",
                            "pe",
                            "gqeberha",
                            "n2",
                            "transfer",
                            "airport",
                        ],
                        "Should give directions to Camp Figtree",
                    ),
                ],
            },
            {
                "message": "I'd like to book for 2 guests, March 20-23",
                "description": "Booking with details",
                "checks": [
                    ("not_contains", "which property", "Should NOT ask which property"),
                    (
                        "contains_any",
                        ["camp figtree", "booking", "reserv", "march", "contact", "email"],
                        "Should acknowledge Camp Figtree booking",
                    ),
                ],
            },
            {
                "message": "What about the restaurant menu?",
                "description": "Still Camp Figtree context",
                "checks": [
                    ("not_contains", "which property", "Should NOT ask which property"),
                ],
            },
            {
                "message": "Is there a spa?",
                "description": "Still Camp Figtree",
                "checks": [
                    ("not_contains", "which property", "Should NOT ask which property"),
                ],
            },
            {
                "message": "What's the weather like in that area?",
                "description": "Regional question, Addo area",
                "checks": [
                    ("not_contains", "which property", "Should NOT ask which property"),
                ],
            },
            {
                "message": "OK great, can you remind me of the rates again?",
                "description": "Circle back to rates (still Camp Figtree)",
                "checks": [
                    ("not_contains", "which property", "Should NOT ask which property"),
                    ("scope_is", "property", "Scope should stay PROPERTY"),
                ],
            },
        ],
    },
    # ── Conversation 3: Minimal KB property -> context switch -> return ──
    {
        "id": "CONV3",
        "name": "Sparse KB + Context Switch (Burlington Bush -> Blackheath -> back)",
        "turns": [
            {
                "message": "Hey, tell me about Burlington Bush",
                "description": "Direct property query (sparse KB)",
                "checks": [
                    ("contains", "burlington", "Should discuss Burlington Bush"),
                    ("property_is", "burlington_bush", "Property should be burlington_bush"),
                ],
            },
            {
                "message": "What kind of cottages do they have?",
                "description": "'they' = Burlington Bush",
                "checks": [
                    ("not_contains", "which property", "Should NOT ask which property"),
                    (
                        "contains_any",
                        ["cottage", "accommodation", "room", "sleep"],
                        "Should discuss Burlington Bush cottages",
                    ),
                ],
            },
            {
                "message": "What are the check-in and check-out times?",
                "description": "Policy question (sparse KB — might not have answer)",
                "checks": [
                    (
                        "not_contains",
                        "which property",
                        "Should NOT ask which property — should say 'I don't have that info' instead",
                    ),
                ],
            },
            {
                "message": "What's the cancellation policy?",
                "description": "Another policy question (still Burlington Bush)",
                "checks": [
                    ("not_contains", "which property", "Should NOT ask which property"),
                ],
            },
            {
                "message": "Actually, let me also ask about Blackheath Lodge",
                "description": "Context switch to new property",
                "checks": [
                    (
                        "contains_any",
                        ["blackheath", "lodge", "sea point", "cape town"],
                        "Should discuss Blackheath Lodge",
                    ),
                    ("property_is", "blackheath_lodge", "Property should switch to blackheath"),
                ],
            },
            {
                "message": "What rooms do they have?",
                "description": "'they' = Blackheath Lodge (NEW context)",
                "checks": [
                    ("not_contains", "which property", "Should NOT ask which property"),
                    ("property_is", "blackheath_lodge", "Should stay on Blackheath"),
                ],
            },
            {
                "message": "And the rates?",
                "description": "Rates for Blackheath (current context)",
                "checks": [
                    ("not_contains", "which property", "Should NOT ask which property"),
                    ("property_is", "blackheath_lodge", "Should stay on Blackheath"),
                ],
            },
            {
                "message": "Going back to Burlington Bush — what activities are nearby?",
                "description": "Explicit context switch back",
                "checks": [
                    (
                        "contains_any",
                        ["burlington", "salem", "activit"],
                        "Should discuss Burlington Bush area",
                    ),
                    ("property_is", "burlington_bush", "Property should switch back"),
                ],
            },
            {
                "message": "And how do I get there?",
                "description": "'there' = Burlington Bush (just switched back)",
                "checks": [
                    ("not_contains", "which property", "Should NOT ask which property"),
                    ("property_is", "burlington_bush", "Should stay on Burlington Bush"),
                ],
            },
            {
                "message": "Perfect. What's the best time of year to visit?",
                "description": "Still Burlington Bush context",
                "checks": [
                    ("not_contains", "which property", "Should NOT ask which property"),
                ],
            },
        ],
    },
]


# ── Check functions ──────────────────────────────────────────────────────── #


def run_check(check_tuple: tuple, response: str, turn_data: dict) -> tuple[bool, str]:
    """Run a single check against the response."""
    check_type = check_tuple[0]

    if check_type == "contains":
        keyword = check_tuple[1].lower()
        reason = check_tuple[2]
        passed = keyword in response.lower()
        return passed, reason

    if check_type == "not_contains":
        keyword = check_tuple[1].lower()
        reason = check_tuple[2]
        passed = keyword not in response.lower()
        return passed, reason

    if check_type == "contains_any":
        keywords = check_tuple[1]
        reason = check_tuple[2]
        passed = any(k.lower() in response.lower() for k in keywords)
        return passed, reason

    if check_type == "scope_is":
        expected_scope = check_tuple[1]
        reason = check_tuple[2]
        actual_scope = turn_data.get("scope", "")
        passed = actual_scope == expected_scope
        if not passed:
            reason = f"{reason} (got: {actual_scope})"
        return passed, reason

    if check_type == "property_is":
        expected_pid = check_tuple[1]
        reason = check_tuple[2]
        actual_pid = turn_data.get("property_id", "")
        passed = actual_pid == expected_pid
        if not passed:
            reason = f"{reason} (got: {actual_pid or 'None'})"
        return passed, reason

    return False, f"Unknown check type: {check_type}"


# ── API helpers ──────────────────────────────────────────────────────────── #


def send_message(
    client: httpx.Client,
    base_url: str,
    message: str,
    session_id: str,
) -> dict:
    """Send a chat message and return the full response dict."""
    payload = {
        "message": message,
        "session_id": session_id,
    }
    headers = {}
    if API_KEY:
        headers["X-API-Key"] = API_KEY

    resp = client.post(
        f"{base_url}/chat",
        json=payload,
        headers=headers,
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


# ── Main runner ──────────────────────────────────────────────────────────── #


def run_conversation(
    client: httpx.Client,
    base_url: str,
    conv: dict,
    *,
    verbose: bool = True,
) -> dict:
    """Run a single multi-turn conversation and return results."""
    session_id = f"eval_{uuid.uuid4().hex[:12]}"
    results = {
        "id": conv["id"],
        "name": conv["name"],
        "session_id": session_id,
        "turns": [],
        "total_checks": 0,
        "passed_checks": 0,
        "failed_checks": 0,
    }

    if verbose:
        print(f"\n{'='*70}")
        print(f"  {conv['id']}: {conv['name']}")
        print(f"  Session: {session_id}")
        print(f"{'='*70}")

    for i, turn in enumerate(conv["turns"]):
        turn_num = i + 1
        message = turn["message"]
        description = turn["description"]
        checks = turn.get("checks", [])

        t0 = time.perf_counter()
        try:
            data = send_message(client, base_url, message, session_id)
        except Exception as e:
            if verbose:
                print(f"\n  T{turn_num:02d} ERROR: {e}")
            results["turns"].append(
                {
                    "turn": turn_num,
                    "message": message,
                    "error": str(e),
                    "checks_passed": 0,
                    "checks_failed": len(checks),
                }
            )
            results["total_checks"] += len(checks)
            results["failed_checks"] += len(checks)
            continue

        elapsed = time.perf_counter() - t0
        response = data.get("response", "")
        scope = data.get("scope", "")
        property_id = data.get("property_id", "")
        session_id = data.get("session_id", session_id)  # Update from response

        # Run checks
        turn_passed = 0
        turn_failed = 0
        check_results = []
        for check in checks:
            passed, reason = run_check(check, response, data)
            check_results.append({"passed": passed, "reason": reason})
            if passed:
                turn_passed += 1
            else:
                turn_failed += 1

        results["total_checks"] += len(checks)
        results["passed_checks"] += turn_passed
        results["failed_checks"] += turn_failed

        turn_result = {
            "turn": turn_num,
            "message": message,
            "description": description,
            "response": response[:200],
            "scope": scope,
            "property_id": property_id,
            "elapsed_s": round(elapsed, 1),
            "checks_passed": turn_passed,
            "checks_failed": turn_failed,
            "check_details": check_results,
        }
        results["turns"].append(turn_result)

        # Print turn result
        if verbose:
            marker = "[+]" if turn_failed == 0 else "[X]"
            scope_tag = f"[{scope or '?':8s}]"
            pid_tag = f"[{property_id or 'none':18s}]"
            print(
                f"\n  {marker} T{turn_num:02d} ({elapsed:4.1f}s) "
                f"{scope_tag} {pid_tag} {description}"
            )
            # Truncate user message
            print(f"      User: {message}")
            # Truncate response
            resp_preview = response.replace("\n", " ")[:120]
            print(f"      Bot:  {resp_preview}")
            # Show failed checks
            for cr in check_results:
                if not cr["passed"]:
                    print(f"      FAIL: {cr['reason']}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate conversation continuity across multi-turn sessions"
    )
    parser.add_argument(
        "--target",
        default=DEFAULT_TARGET,
        help=f"API base URL (default: {DEFAULT_TARGET})",
    )
    parser.add_argument(
        "--conv",
        help="Run a specific conversation by ID (e.g., CONV1)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only show summary",
    )
    args = parser.parse_args()

    base_url = args.target.rstrip("/")
    verbose = not args.quiet

    print(f"Target: {base_url}")

    # Health check
    try:
        with httpx.Client() as client:
            resp = client.get(f"{base_url}/health", timeout=5)
            health = resp.json()
            if health.get("status") != "healthy":
                print(f"WARNING: API not healthy: {health}")
    except Exception as e:
        print(f"ERROR: Cannot reach API at {base_url}: {e}")
        sys.exit(1)

    # Filter conversations
    convs = CONVERSATIONS
    if args.conv:
        convs = [c for c in convs if c["id"] == args.conv.upper()]
        if not convs:
            print(f"ERROR: Conversation '{args.conv}' not found")
            print(f"Available: {', '.join(c['id'] for c in CONVERSATIONS)}")
            sys.exit(1)

    # Run conversations
    all_results = []
    total_checks = 0
    total_passed = 0
    total_failed = 0
    start = time.perf_counter()

    with httpx.Client() as client:
        for conv in convs:
            result = run_conversation(client, base_url, conv, verbose=verbose)
            all_results.append(result)
            total_checks += result["total_checks"]
            total_passed += result["passed_checks"]
            total_failed += result["failed_checks"]

    elapsed = time.perf_counter() - start

    # ── Summary ──────────────────────────────────────────────────────────── #
    print(f"\n{'='*70}")
    print("  CONVERSATION CONTINUITY RESULTS")
    print(f"{'='*70}")

    for result in all_results:
        conv_status = "PASS" if result["failed_checks"] == 0 else "FAIL"
        passed = result["passed_checks"]
        total = result["total_checks"]
        pct = round(100 * passed / total) if total else 0
        print(
            f"  {conv_status:4s}  {result['id']}  "
            f"{result['name'][:45]:45s}  "
            f"{passed}/{total} checks ({pct}%)"
        )

        # Show failed turns
        if result["failed_checks"] > 0:
            for turn in result["turns"]:
                if turn.get("checks_failed", 0) > 0:
                    for cd in turn.get("check_details", []):
                        if not cd["passed"]:
                            print(f"        T{turn['turn']:02d}: {cd['reason']}")

    print(
        f"\n  Total: {total_passed}/{total_checks} checks passed "
        f"({round(100*total_passed/total_checks) if total_checks else 0}%)"
    )
    print(f"  Conversations: {len(all_results)}")
    print(f"  Elapsed: {elapsed:.1f}s")

    # Exit code
    if total_failed > 0:
        print(f"\n  {total_failed} FAILED checks")
        sys.exit(1)
    else:
        print("\n  ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
