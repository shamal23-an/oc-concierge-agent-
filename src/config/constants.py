from __future__ import annotations

# Retrieval
MAX_CHUNKS_PER_QUERY = 10
MIN_CHUNKS_FOR_CONFIDENCE = 2
SCORE_THRESHOLD_PROPERTY = 0.30
SCORE_THRESHOLD_REGION = 0.25
SCORE_THRESHOLD_SHARED = 0.20

# Caching
RESPONSE_CACHE_TTL = 3600  # 1 hour
RETRIEVAL_CACHE_TTL = 3600  # 1 hour
EMBEDDING_CACHE_TTL = 86400  # 24 hours
EMBEDDING_CACHE_MAX_SIZE = 1000

# Session
MAX_CONVERSATION_HISTORY = 20
SESSION_LOCK_TTL = 10  # seconds — auto-expire stale locks
SESSION_LOCK_WAIT_TIMEOUT = 5  # seconds — max wait for lock acquisition
SESSION_LOCK_POLL_INTERVAL = 0.1  # seconds — polling interval while waiting

# Ingestion
BATCH_EMBEDDING_SIZE = 100
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".msg", ".xlsx", ".xls"}

# Greeting keywords (fast-path, skip LLM)
GREETING_PATTERNS = {
    "hello",
    "hi",
    "hey",
    "good morning",
    "good afternoon",
    "good evening",
    "howdy",
    "greetings",
    "hiya",
    "morning",
    "afternoon",
    "evening",
}

# Out-of-scope patterns
OUT_OF_SCOPE_PATTERNS = {
    "write code",
    "python",
    "javascript",
    "math problem",
    "solve equation",
    "translate to",
    "who is the president",
    "capital of",
}

# Booking intent patterns (trigger lead capture flow)
BOOKING_PATTERNS = {
    "book",
    "booking",
    "reserve",
    "reservation",
    "availability",
    "available dates",
    "check in",
    "check-in",
    "check out",
    "check-out",
    "i want to stay",
    "make a reservation",
    "book a room",
    "book a stay",
}
