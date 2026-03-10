"""In-memory metrics counters for observability."""

from __future__ import annotations

import statistics
import threading
import time
from collections import deque
from dataclasses import dataclass, field


@dataclass
class _LatencyBuffer:
    """Thread-safe circular buffer for latency samples."""

    _samples: deque[float] = field(default_factory=lambda: deque(maxlen=1000))
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def record(self, value_ms: float) -> None:
        with self._lock:
            self._samples.append(value_ms)

    def percentile(self, p: float) -> float:
        with self._lock:
            if not self._samples:
                return 0.0
            sorted_s = sorted(self._samples)
            idx = int(len(sorted_s) * p / 100)
            idx = min(idx, len(sorted_s) - 1)
            return round(sorted_s[idx], 1)

    def avg(self) -> float:
        with self._lock:
            if not self._samples:
                return 0.0
            return round(statistics.mean(self._samples), 1)

    def count(self) -> int:
        with self._lock:
            return len(self._samples)


class Metrics:
    """Application-wide metrics singleton."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queries_total = 0
        self._queries_by_scope: dict[str, int] = {}
        self._denials = 0
        self._cache_hits = 0
        self._cache_misses = 0
        self._errors = 0

        self.retrieval_latency = _LatencyBuffer()
        self.rerank_latency = _LatencyBuffer()
        self.llm_latency = _LatencyBuffer()
        self.total_latency = _LatencyBuffer()

        self._top_scores: deque[float] = deque(maxlen=1000)
        self._chunks_returned: deque[int] = deque(maxlen=1000)

        self._started_at = time.time()

    def record_query(self, scope: str) -> None:
        with self._lock:
            self._queries_total += 1
            self._queries_by_scope[scope] = self._queries_by_scope.get(scope, 0) + 1

    def record_denial(self) -> None:
        with self._lock:
            self._denials += 1

    def record_cache_hit(self) -> None:
        with self._lock:
            self._cache_hits += 1

    def record_cache_miss(self) -> None:
        with self._lock:
            self._cache_misses += 1

    def record_error(self) -> None:
        with self._lock:
            self._errors += 1

    def record_retrieval_result(self, top_score: float, num_chunks: int) -> None:
        with self._lock:
            self._top_scores.append(top_score)
            self._chunks_returned.append(num_chunks)

    def snapshot(self) -> dict:
        """Return current metrics as a JSON-serializable dict."""
        with self._lock:
            total = self._queries_total
            cache_total = self._cache_hits + self._cache_misses

            return {
                "uptime_seconds": round(time.time() - self._started_at),
                "queries_total": total,
                "queries_by_scope": dict(self._queries_by_scope),
                "denial_rate": round(self._denials / total, 3) if total else 0,
                "cache_hit_rate": (round(self._cache_hits / cache_total, 3) if cache_total else 0),
                "errors_total": self._errors,
                "latency": {
                    "retrieval_p50_ms": self.retrieval_latency.percentile(50),
                    "retrieval_p95_ms": self.retrieval_latency.percentile(95),
                    "rerank_p50_ms": self.rerank_latency.percentile(50),
                    "rerank_p95_ms": self.rerank_latency.percentile(95),
                    "llm_p50_ms": self.llm_latency.percentile(50),
                    "llm_p95_ms": self.llm_latency.percentile(95),
                    "total_p50_ms": self.total_latency.percentile(50),
                    "total_p95_ms": self.total_latency.percentile(95),
                },
                "retrieval": {
                    "top_score_avg": (
                        round(statistics.mean(self._top_scores), 3) if self._top_scores else 0
                    ),
                    "chunks_returned_avg": (
                        round(statistics.mean(self._chunks_returned), 1)
                        if self._chunks_returned
                        else 0
                    ),
                },
            }


# Singleton
_metrics: Metrics | None = None


def get_metrics() -> Metrics:
    global _metrics
    if _metrics is None:
        _metrics = Metrics()
    return _metrics
