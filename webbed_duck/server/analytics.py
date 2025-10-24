"""Runtime analytics collection for route popularity and performance."""
from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Dict


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


__all__ = ["AnalyticsStore", "RouteMetrics"]
