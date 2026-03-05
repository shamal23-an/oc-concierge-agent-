from __future__ import annotations

import json
from unittest.mock import AsyncMock

from src.cache.response_cache import (
    _build_cache_key,
    get_cached_response,
    get_cached_retrieval,
    set_cached_response,
    set_cached_retrieval,
)

# ── Key generation (sync — no change needed) ─────────────────────────────── #


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


# ── Response cache (async) ────────────────────────────────────────────────── #


class TestResponseCache:
    async def test_miss_returns_none(self):
        redis = AsyncMock()
        redis.get.return_value = None
        result = await get_cached_response(redis, "hello", None, "group")
        assert result is None

    async def test_hit_returns_dict(self):
        payload = {"response": "Welcome!", "sources": ["menu.pdf"]}
        redis = AsyncMock()
        redis.get.return_value = json.dumps(payload)
        result = await get_cached_response(redis, "hello", None, "group")
        assert result == payload

    async def test_hit_bytes_returns_dict(self):
        """Upstash Redis returns bytes — decode before json.loads."""
        payload = {"response": "Welcome!", "sources": ["menu.pdf"]}
        redis = AsyncMock()
        redis.get.return_value = json.dumps(payload).encode("utf-8")
        result = await get_cached_response(redis, "hello", None, "group")
        assert result == payload

    async def test_set_calls_setex(self):
        redis = AsyncMock()
        await set_cached_response(
            redis,
            "hello",
            None,
            "group",
            response="Welcome!",
            sources=["menu.pdf"],
        )
        redis.setex.assert_called_once()
        args = redis.setex.call_args
        assert args[0][1] == 3600  # RESPONSE_CACHE_TTL
        stored = json.loads(args[0][2])
        assert stored["response"] == "Welcome!"
        assert stored["sources"] == ["menu.pdf"]

    async def test_redis_error_returns_none(self):
        """Cache read errors degrade gracefully to a miss."""
        redis = AsyncMock()
        redis.get.side_effect = ConnectionError("Redis down")
        result = await get_cached_response(redis, "hello", None, "group")
        assert result is None

    async def test_corrupt_data_returns_none(self):
        """Corrupted cache data degrades gracefully to a miss."""
        redis = AsyncMock()
        redis.get.return_value = b"not-valid-json{{"
        result = await get_cached_response(redis, "hello", None, "group")
        assert result is None

    async def test_redis_write_error_does_not_raise(self):
        """Cache write errors are swallowed (don't break the request)."""
        redis = AsyncMock()
        redis.setex.side_effect = ConnectionError("Redis down")
        await set_cached_response(
            redis,
            "hello",
            None,
            "group",
            response="Welcome!",
            sources=[],
        )


# ── Retrieval cache (async) ──────────────────────────────────────────────── #


class TestRetrievalCache:
    async def test_miss_returns_none(self):
        redis = AsyncMock()
        redis.get.return_value = None
        result = await get_cached_retrieval(redis, "hello", None, "group")
        assert result is None

    async def test_hit_returns_chunks(self):
        chunks = [
            {
                "content": "Dinner is at 7pm",
                "score": 0.9,
                "property_ids": ["la_fontaine"],
                "source_file": "menu.pdf",
                "metadata": {},
            },
        ]
        redis = AsyncMock()
        redis.get.return_value = json.dumps(chunks)
        result = await get_cached_retrieval(redis, "hello", None, "group")
        assert result == chunks

    async def test_hit_bytes_returns_chunks(self):
        """Upstash Redis returns bytes — decode before json.loads."""
        chunks = [
            {
                "content": "Dinner is at 7pm",
                "score": 0.9,
                "property_ids": ["la_fontaine"],
                "source_file": "menu.pdf",
                "metadata": {},
            },
        ]
        redis = AsyncMock()
        redis.get.return_value = json.dumps(chunks).encode("utf-8")
        result = await get_cached_retrieval(redis, "hello", None, "group")
        assert result == chunks

    async def test_set_calls_setex(self):
        redis = AsyncMock()
        chunks = [
            {
                "content": "Dinner is at 7pm",
                "score": 0.9,
                "property_ids": ["la_fontaine"],
                "source_file": "menu.pdf",
                "metadata": {},
            },
        ]
        await set_cached_retrieval(
            redis,
            "hello",
            None,
            "group",
            chunks=chunks,
        )
        redis.setex.assert_called_once()
        args = redis.setex.call_args
        assert args[0][1] == 3600  # RETRIEVAL_CACHE_TTL
