"""Tests for observability metrics."""

from __future__ import annotations

from src.observability.metrics import Metrics


class TestMetrics:
    def test_initial_snapshot(self):
        m = Metrics()
        snap = m.snapshot()
        assert snap["queries_total"] == 0
        assert snap["denial_rate"] == 0
        assert snap["cache_hit_rate"] == 0

    def test_record_query(self):
        m = Metrics()
        m.record_query("property")
        m.record_query("property")
        m.record_query("region")
        snap = m.snapshot()
        assert snap["queries_total"] == 3
        assert snap["queries_by_scope"]["property"] == 2
        assert snap["queries_by_scope"]["region"] == 1

    def test_denial_rate(self):
        m = Metrics()
        m.record_query("property")
        m.record_query("property")
        m.record_denial()
        snap = m.snapshot()
        assert snap["denial_rate"] == 0.5

    def test_cache_hit_rate(self):
        m = Metrics()
        m.record_cache_hit()
        m.record_cache_miss()
        m.record_cache_miss()
        snap = m.snapshot()
        assert abs(snap["cache_hit_rate"] - 0.333) < 0.01

    def test_latency_recording(self):
        m = Metrics()
        m.retrieval_latency.record(100.0)
        m.retrieval_latency.record(200.0)
        m.retrieval_latency.record(300.0)
        snap = m.snapshot()
        assert snap["latency"]["retrieval_p50_ms"] > 0

    def test_retrieval_result(self):
        m = Metrics()
        m.record_retrieval_result(0.85, 5)
        m.record_retrieval_result(0.90, 7)
        snap = m.snapshot()
        assert snap["retrieval"]["top_score_avg"] > 0.8
        assert snap["retrieval"]["chunks_returned_avg"] == 6.0

    def test_uptime(self):
        m = Metrics()
        snap = m.snapshot()
        assert snap["uptime_seconds"] >= 0
