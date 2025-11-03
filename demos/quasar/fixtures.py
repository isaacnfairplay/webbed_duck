"""Data fixture helpers for the Quasar demos."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable, Dict, Iterable, List, Mapping


@dataclass
class Fixture:
    """Simple wrapper describing a fixture generator."""

    name: str
    description: str
    factory: Callable[[], List[Mapping[str, object]]]

    def generate(self) -> List[Mapping[str, object]]:
        return self.factory()


def _daily_timeseries(days: int = 10) -> List[Mapping[str, object]]:
    start = date(2024, 1, 1)
    return [
        {"date": start + timedelta(days=i), "value": (i + 1) * 3}
        for i in range(days)
    ]


def _category_breakdown() -> List[Mapping[str, object]]:
    categories = ["alpha", "beta", "gamma", "delta"]
    return [{"category": cat, "value": (idx + 1) * 5} for idx, cat in enumerate(categories)]


def build_fixtures() -> Dict[str, Fixture]:
    """Return the default fixture catalog."""

    timeseries = Fixture(
        name="timeseries",
        description="Simple monotonically increasing daily values",
        factory=_daily_timeseries,
    )
    categories = Fixture(
        name="categories",
        description="Categorical breakdown for column charts",
        factory=_category_breakdown,
    )
    return {fixture.name: fixture for fixture in (timeseries, categories)}


def preview_fixture_rows(fixtures: Iterable[Fixture], limit: int = 3) -> Dict[str, List[Mapping[str, object]]]:
    """Materialise a preview of the provided fixtures."""

    return {fixture.name: fixture.generate()[:limit] for fixture in fixtures}
