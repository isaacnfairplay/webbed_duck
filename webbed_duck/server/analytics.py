"""Runtime analytics collection for route popularity and performance."""
from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Dict, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import for type checking only
    from .app import RouteExecutionResult


@dataclass(slots=True)
class RouteMetrics:
    """Aggregated metrics for a single route."""

    hits: int = 0
    total_rows: int = 0
    total_latency_ms: float = 0.0
    interactions: int = 0

    def snapshot(self) -> dict[str, float | int]:
        avg_latency = self.total_latency_ms / self.hits if self.hits else 0.0
        return {
            "hits": self.hits,
            "rows": self.total_rows,
            "avg_latency_ms": round(avg_latency, 3),
            "interactions": self.interactions,
        }


@dataclass(slots=True)
class ExecutionMetrics:
    """Execution measurements that can be recorded for analytics."""

    rows_returned: int
    latency_ms: float
    interactions: int = 0

    @classmethod
    def from_execution_result(
        cls, result: "RouteExecutionResult", *, interactions: int
    ) -> "ExecutionMetrics":
        """Build metrics from a :class:`RouteExecutionResult` instance."""

        return cls(
            rows_returned=result.total_rows,
            latency_ms=result.elapsed_ms,
            interactions=interactions,
        )


class AnalyticsStore:
    """Track route interaction counts for popularity-weighted folders."""

    def __init__(self, weight: int = 1, *, enabled: bool = True) -> None:
        self._metrics: Dict[str, RouteMetrics] = {}
        self._weight = max(1, int(weight))
        self._enabled = bool(enabled)
        self._lock = Lock()

    def record(
        self,
        route_id: str,
        *,
        rows_returned: int,
        latency_ms: float,
        interactions: int,
    ) -> None:
        if not self._enabled:
            return
        with self._lock:
            metrics = self._metrics.setdefault(route_id, RouteMetrics())
            metrics.hits += self._weight
            metrics.total_rows += max(0, int(rows_returned))
            metrics.total_latency_ms += max(0.0, float(latency_ms))
            metrics.interactions = max(metrics.interactions, int(interactions))

    def record_execution(self, route_id: str, metrics: ExecutionMetrics) -> None:
        """Record analytics data using a structured metrics payload."""

        self.record(
            route_id,
            rows_returned=metrics.rows_returned,
            latency_ms=metrics.latency_ms,
            interactions=metrics.interactions,
        )

    def snapshot(self) -> Dict[str, dict[str, float | int]]:
        with self._lock:
            return {route_id: metrics.snapshot() for route_id, metrics in self._metrics.items()}

    def get(self, route_id: str) -> RouteMetrics | None:
        with self._lock:
            metrics = self._metrics.get(route_id)
            if not metrics:
                return None
            return RouteMetrics(
                hits=metrics.hits,
                total_rows=metrics.total_rows,
                total_latency_ms=metrics.total_latency_ms,
                interactions=metrics.interactions,
            )

    def reset(self) -> None:
        with self._lock:
            self._metrics.clear()


__all__ = ["AnalyticsStore", "RouteMetrics", "ExecutionMetrics"]
