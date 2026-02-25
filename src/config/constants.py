from __future__ import annotations

# Retrieval
MAX_CHUNKS_PER_QUERY = 10
MIN_CHUNKS_FOR_CONFIDENCE = 2
SCORE_THRESHOLD_PROPERTY = 0.75
SCORE_THRESHOLD_REGION = 0.65
SCORE_THRESHOLD_SHARED = 0.55

# Caching
RESPONSE_CACHE_TTL = 3600  # 1 hour
EMBEDDING_CACHE_TTL = 86400  # 24 hours
EMBEDDING_CACHE_MAX_SIZE = 1000

# Session
MAX_CONVERSATION_HISTORY = 20

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
