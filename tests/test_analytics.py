from dataclasses import dataclass

import pytest

from webbed_duck.server.analytics import AnalyticsStore, ExecutionMetrics


@dataclass
class _FakeResult:
    total_rows: int
    elapsed_ms: float


def test_record_execution_applies_weight_and_clamps() -> None:
    store = AnalyticsStore(weight=3, enabled=True)
    metrics = ExecutionMetrics(rows_returned=5, latency_ms=12.5, interactions=2)
    store.record_execution("demo", metrics)

    snapshot = store.snapshot()
    assert snapshot["demo"]["hits"] == 3
    assert snapshot["demo"]["rows"] == 5
    assert snapshot["demo"]["avg_latency_ms"] == pytest.approx(12.5 / 3, rel=1e-3)
    assert snapshot["demo"]["interactions"] == 2

    copy = store.get("demo")
    assert copy is not None
    copy.hits = 999
    assert store.snapshot()["demo"]["hits"] == 3


def test_record_execution_uses_factory() -> None:
    store = AnalyticsStore(weight=1, enabled=True)
    result = _FakeResult(total_rows=7, elapsed_ms=45.0)
    metrics = ExecutionMetrics.from_execution_result(result, interactions=4)
    store.record_execution("demo", metrics)
    data = store.snapshot()["demo"]
    assert data["rows"] == 7
    assert data["avg_latency_ms"] == pytest.approx(45.0)
    assert data["interactions"] == 4


def test_reset_and_disabled_store() -> None:
    store = AnalyticsStore(weight=2, enabled=False)
    store.record_execution("demo", ExecutionMetrics(rows_returned=10, latency_ms=20.0, interactions=1))
    assert store.snapshot() == {}

    enabled_store = AnalyticsStore(weight=2, enabled=True)
    enabled_store.record_execution("demo", ExecutionMetrics(rows_returned=-5, latency_ms=-10.0, interactions=-3))
    assert enabled_store.snapshot()["demo"]["rows"] == 0
    assert enabled_store.snapshot()["demo"]["avg_latency_ms"] == 0.0
    assert enabled_store.snapshot()["demo"]["interactions"] == 0
    enabled_store.reset()
    assert enabled_store.snapshot() == {}
