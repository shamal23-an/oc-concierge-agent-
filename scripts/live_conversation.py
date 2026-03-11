"""Live conversation test - prints each message and response step by step.

Run:
    uv run python scripts/live_conversation.py
    uv run python scripts/live_conversation.py --target https://your-railway-url.up.railway.app
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

MESSAGES = [
    # Greeting
    "Hey there!",
    # Discovery
    "I love wine and fine dining, where should I go?",
    # Pick property
    "La Fontaine sounds great, tell me more",
    # Rates (context retention)
    "What are the rates?",
    # Room types (anaphoric 'they')
    "What room types do they have?",
    # Spa
    "Do they have spa treatments?",
    # Out of scope
    "What is the capital of France?",
    # Return to property after OOS
    "OK sorry, back to La Fontaine. What is the check-in time?",
    # Policy follow-up
    "And the cancellation policy?",
    # Booking intent
    "I want to book the Luxury Suite for 2 guests, April 15-18",
    # Breakfast
    "Is breakfast included?",
    # Switch property
    "Actually tell me about Camp Figtree too",
    # Activities (should be Camp Figtree)
    "What activities do they offer?",
    # THE critical test - 'rates for the same'
    "What are the rates for the same?",
    # Directions (anaphoric 'there')
    "How do I get there from PE airport?",
    # Book Camp Figtree
    "Can I book 3 nights for 2 guests in May?",
    # Switch to POD
    "What about POD Camps Bay? How does it compare?",
    # Rooms at POD (context retention on new property)
    "What rooms do they have?",
    # Random irrelevant
    "Can you write me a song?",
    # Complaint / escalation
    "I had a bad experience at one of your properties, who do I complain to?",
    # General policy
    "What payment methods do you accept?",
    # Back to planning
    "So for our trip: 3 nights La Fontaine, 2 nights POD, "
    "3 nights Camp Figtree. Summarize the plan.",
    # WiFi
    "Is there WiFi at all the properties?",
    # Goodbye
    "Perfect, thanks for all the help! Goodbye!",
]


def main():
    parser = argparse.ArgumentParser(description="Live conversation test")
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
            print(f"API not healthy: {health}")
            sys.exit(1)
    except Exception as e:
        print(f"Cannot reach API at {base_url}: {e}")
        sys.exit(1)

    # Flush Redis
    try:
        import redis

        r = redis.Redis()
        r.flushall()
        print("Redis flushed.\n")
    except Exception:
        print("Could not flush Redis, continuing...\n")

    session_id = f"live_{uuid.uuid4().hex[:8]}"
    headers = {"X-API-Key": API_KEY} if API_KEY else {}
    client = httpx.Client()

    print("=" * 70)
    print(f"  LIVE CONVERSATION TEST - {len(MESSAGES)} messages")
    print(f"  Target: {base_url}")
    print(f"  Session: {session_id}")
    print("=" * 70)

    for i, message in enumerate(MESSAGES):
        turn = i + 1

        print(f"\n{'- ' * 35}")
        print(f"  T{turn:02d} | GUEST: {message}")
        print(f"{'- ' * 35}")

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
            print(f"  ERROR: {e}")
            continue

        elapsed = time.perf_counter() - t0
        session_id = data.get("session_id", session_id)

        response = data.get("response", "")
        scope = data.get("scope", "-")
        prop_id = data.get("property_id", "-") or "-"
        sources = data.get("sources", [])
        cached = data.get("cached", False)

        # Print metadata
        print(
            f"  Scope: {scope:15s} | Property: {prop_id:20s} | "
            f"Time: {elapsed:.1f}s" + (" | CACHED" if cached else "")
        )

        # Print response with wrapping
        print()
        lines = response.split("\n")
        for line in lines:
            # Wrap long lines
            while len(line) > 90:
                print(f"  {line[:90]}")
                line = line[90:]
            print(f"  {line}")

        if sources:
            print(f"\n  Sources: {', '.join(sources)}")

        # Pause so user can read
        if turn < len(MESSAGES):
            try:
                input("\n  [Press Enter for next message...]")
            except (KeyboardInterrupt, EOFError):
                print("\n\nStopped.")
                break

    client.close()
    print(f"\n{'=' * 70}")
    print("  CONVERSATION COMPLETE")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    main()
