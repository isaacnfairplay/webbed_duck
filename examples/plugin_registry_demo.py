"""Demonstrate registering plugins outside the main webbed_duck package.

This module avoids importing the FastAPI application and shows how a caller can
register plugins from a standalone script or tests. The demo keeps all
interactions outside the main package source so it can be used as a lightweight
reference implementation for bespoke deployments.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pyarrow as pa

from webbed_duck.plugins.assets import register_image_getter, resolve_image
from webbed_duck.plugins.charts import register_chart_renderer, render_route_charts


@dataclass
class DemoRoute:
    """Simple container describing a demo route and the assets it uses."""

    route_id: str
    hero_image: str
    charts: Iterable[dict[str, object]]


def install_demo_plugins() -> None:
    """Install demo plugins for documentation and exploratory testing."""

    @register_image_getter("demo_cdn")
    def _demo_cdn(name: str, route_id: str) -> str:
        return f"https://cdn.intra.example/{route_id}/{name}"

    @register_chart_renderer("totalizer")
    def _totalizer(table: pa.Table, spec: dict[str, object]) -> str:
        column = str(spec.get("y", ""))
        if column not in table.column_names:
            return f"<pre>Missing column: {column}</pre>"
        values = table.column(column).to_pylist()
        total = sum(float(value) for value in values)
        label = spec.get("title", "Total")
        return f"<div class='chart-card'><h4>{label}</h4><p>{total:.2f}</p></div>"


def render_demo(route: DemoRoute) -> dict[str, object]:
    """Return the resolved image URL and rendered charts for ``route``."""

    hero_url = resolve_image(route.hero_image, route.route_id, "demo_cdn")
    table = pa.table({"value": [1, 2, 3, 4]})
    charts = render_route_charts(table, route.charts)
    return {"hero": hero_url, "charts": charts}


if __name__ == "__main__":  # pragma: no cover - manual demo
    install_demo_plugins()
    demo_route = DemoRoute(
        route_id="routes/overview",
        hero_image="overview.png",
        charts=[{"type": "totalizer", "id": "total", "title": "Total Value", "y": "value"}],
    )
    payload = render_demo(demo_route)
    print("Hero:", payload["hero"])
    for chart in payload["charts"]:
        print(f"Chart {chart['id']} -> {chart['html']}")
