from __future__ import annotations

from collections import Counter
from threading import Lock
from typing import Dict


class AnalyticsStore:
    """Track route interaction counts for popularity-weighted folders."""

    def __init__(self, weight: int = 1) -> None:
        self._counter: Counter[str] = Counter()
        self._weight = max(1, int(weight))
        self._lock = Lock()

    def record(self, route_id: str) -> None:
        with self._lock:
            self._counter[route_id] += self._weight

    def snapshot(self) -> Dict[str, int]:
        with self._lock:
            return dict(self._counter)

    def reset(self) -> None:
        with self._lock:
            self._counter.clear()


__all__ = ["AnalyticsStore"]
