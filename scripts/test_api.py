"""Quick API test script — avoids Windows curl issues."""

from __future__ import annotations

import sys
import time

import httpx

# Use 127.0.0.1 explicitly — Windows 'localhost' can resolve to IPv6 [::1]
# which may not match the uvicorn bind address.
BASE_URL = "http://127.0.0.1:8000"

QUERIES = [
    "hello",
    "What are the rates at Avondrood?",
    "What activities can I do at Camp Figtree?",
    "I want to book a room at POD Camps Bay",
    "Tell me about Pleasance",
    "What properties do you have?",
    "What spa treatments does La Fontaine offer?",
]


def main() -> None:
    # Allow custom base URL
    base = sys.argv[1] if len(sys.argv) > 1 else BASE_URL
    print(f"Target: {base}\n")

    # Health check
    try:
        r = httpx.get(f"{base}/health", timeout=5)
        print(f"Health: {r.json()}\n")
    except Exception as e:
        print(f"Cannot connect to {base}: {e}")
        return

    for query in QUERIES:
        print(f"Q: {query}")
        start = time.perf_counter()
        try:
            r = httpx.post(
                f"{base}/chat",
                json={"message": query},
                timeout=120,
            )
            elapsed = time.perf_counter() - start

            if r.status_code == 200:
                data = r.json()
                answer = data.get("response", "")
                scope = data.get("scope", "")
                sources = data.get("sources", [])
                cached = data.get("cached", False)
                print(f"A: {answer[:200]}")
                print(f"   scope={scope} sources={sources} cached={cached} time={elapsed:.1f}s")
            else:
                print(f"   ERROR {r.status_code} ({elapsed:.1f}s): {r.text[:300]}")
                print(f"   Headers: {dict(r.headers)}")
        except Exception as e:
            elapsed = time.perf_counter() - start
            print(f"   FAILED ({elapsed:.1f}s): {type(e).__name__}: {e}")
        print()


if __name__ == "__main__":
    main()
