from __future__ import annotations

import json
from unittest.mock import MagicMock

from src.cache.response_cache import (
    _build_cache_key,
    get_cached_response,
    get_cached_retrieval,
    set_cached_response,
    set_cached_retrieval,
)

# ── Key generation ────────────────────────────────────────────────────────── #


class TestBuildCacheKey:
    def test_deterministic(self):
        """Same inputs always produce the same key."""
        k1 = _build_cache_key("What is dinner?", "la_fontaine", "property")
        k2 = _build_cache_key("What is dinner?", "la_fontaine", "property")
        assert k1 == k2

    def test_case_insensitive(self):
        """Normalisation lowercases the message."""
        k1 = _build_cache_key("What is dinner?", "la_fontaine", "property")
        k2 = _build_cache_key("what is dinner?", "la_fontaine", "property")
        assert k1 == k2

    def test_strips_whitespace(self):
        """Leading/trailing whitespace is stripped."""
        k1 = _build_cache_key("hello", None, "group")
        k2 = _build_cache_key("  hello  ", None, "group")
        assert k1 == k2

    def test_different_property_different_key(self):
        """Different property_ids produce different keys."""
        k1 = _build_cache_key("hello", "la_fontaine", "property")
        k2 = _build_cache_key("hello", "pod_camps_bay", "property")
        assert k1 != k2

    def test_different_scope_different_key(self):
        """Different scopes produce different keys."""
        k1 = _build_cache_key("hello", None, "property")
        k2 = _build_cache_key("hello", None, "region")
        assert k1 != k2

    def test_none_property_id(self):
        """None property_id doesn't crash."""
        key = _build_cache_key("hello", None, "group")
        assert isinstance(key, str) and len(key) == 64  # SHA-256 hex


# ── Response cache ────────────────────────────────────────────────────────── #


class TestResponseCache:
    def test_miss_returns_none(self):
        redis = MagicMock()
        redis.get.return_value = None
        result = get_cached_response(redis, "hello", None, "group")
        assert result is None

    def test_hit_returns_dict(self):
        payload = {"response": "Welcome!", "sources": ["menu.pdf"]}
        redis = MagicMock()
        redis.get.return_value = json.dumps(payload)
        result = get_cached_response(redis, "hello", None, "group")
        assert result == payload

    def test_set_calls_setex(self):
        redis = MagicMock()
        set_cached_response(
            redis, "hello", None, "group",
            response="Welcome!", sources=["menu.pdf"],
        )
        redis.setex.assert_called_once()
        args = redis.setex.call_args
        assert args[0][1] == 3600  # RESPONSE_CACHE_TTL
        stored = json.loads(args[0][2])
        assert stored["response"] == "Welcome!"
        assert stored["sources"] == ["menu.pdf"]

    def test_redis_error_returns_none(self):
        """Cache read errors degrade gracefully to a miss."""
        redis = MagicMock()
        redis.get.side_effect = ConnectionError("Redis down")
        result = get_cached_response(redis, "hello", None, "group")
        assert result is None

    def test_redis_write_error_does_not_raise(self):
        """Cache write errors are swallowed (don't break the request)."""
        redis = MagicMock()
        redis.setex.side_effect = ConnectionError("Redis down")
        # Should not raise
        set_cached_response(
            redis, "hello", None, "group",
            response="Welcome!", sources=[],
        )


# ── Retrieval cache ──────────────────────────────────────────────────────── #


class TestRetrievalCache:
    def test_miss_returns_none(self):
        redis = MagicMock()
        redis.get.return_value = None
        result = get_cached_retrieval(redis, "hello", None, "group")
        assert result is None

    def test_hit_returns_chunks(self):
        chunks = [
            {
                "content": "Dinner is at 7pm",
                "score": 0.9,
                "property_ids": ["la_fontaine"],
                "source_file": "menu.pdf",
                "metadata": {},
            },
        ]
        redis = MagicMock()
        redis.get.return_value = json.dumps(chunks)
        result = get_cached_retrieval(redis, "hello", None, "group")
        assert result == chunks

    def test_set_calls_setex(self):
        redis = MagicMock()
        chunks = [
            {
                "content": "Dinner is at 7pm",
                "score": 0.9,
                "property_ids": ["la_fontaine"],
                "source_file": "menu.pdf",
                "metadata": {},
            },
        ]
        set_cached_retrieval(
            redis, "hello", None, "group", chunks=chunks,
        )
        redis.setex.assert_called_once()
        args = redis.setex.call_args
        assert args[0][1] == 3600  # RETRIEVAL_CACHE_TTL
