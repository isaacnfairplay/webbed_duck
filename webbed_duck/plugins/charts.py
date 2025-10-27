from __future__ import annotations

from typing import Callable, Dict, Iterable, Mapping, MutableMapping

import pyarrow as pa

ChartRenderer = Callable[[pa.Table, Mapping[str, object]], str]

_RENDERERS: Dict[str, ChartRenderer] = {}


def register_chart_renderer(chart_type: str) -> Callable[[ChartRenderer], ChartRenderer]:
    """Register a chart renderer for ``chart_type``."""

    def decorator(func: ChartRenderer) -> ChartRenderer:
        _RENDERERS[chart_type] = func
        return func

    return decorator


def get_chart_renderer(chart_type: str) -> ChartRenderer | None:
    return _RENDERERS.get(chart_type)


def render_route_charts(table: pa.Table, specs: Iterable[Mapping[str, object]]) -> list[dict[str, str]]:
    rendered: list[dict[str, str]] = []
    for index, spec in enumerate(specs):
        chart_type = str(spec.get("type", "")).strip()
        if not chart_type:
            continue
        renderer = get_chart_renderer(chart_type)
        if renderer is None:
            continue
        chart_id = str(spec.get("id", f"chart_{index}"))
        try:
            html = renderer(table, spec)
        except Exception as exc:  # pragma: no cover - defensive
            html = f"<pre>Chart '{chart_id}' failed: {exc}</pre>"
        rendered.append({"id": chart_id, "html": html})
    return rendered


@register_chart_renderer("line")
def _render_line(table: pa.Table, spec: Mapping[str, object]) -> str:
    y_col = str(spec.get("y", ""))
    if y_col not in table.column_names:
        return f"<svg viewBox='0 0 400 160'><text x='8' y='80'>Unknown y column: {y_col}</text></svg>"
    y_values = table.column(y_col).to_pylist()
    if not y_values:
        return "<svg viewBox='0 0 400 160'><text x='8' y='80'>No data</text></svg>"
    try:
        numbers = [float(value) for value in y_values]
    except Exception:
        return "<svg viewBox='0 0 400 160'><text x='8' y='80'>Non-numeric data</text></svg>"

    width, height = 400.0, 160.0
    padding = 12.0
    min_y = min(numbers)
    max_y = max(numbers)
    if min_y == max_y:
        max_y += 1.0
        min_y -= 1.0
    span = max_y - min_y
    if span == 0:
        span = 1.0

    step = (width - 2 * padding) / max(1, len(numbers) - 1)
    points = []
    for idx, value in enumerate(numbers):
        x = padding + idx * step
        y = height - padding - ((value - min_y) / span) * (height - 2 * padding)
        points.append(f"{x:.1f},{y:.1f}")

    polyline = " ".join(points)
    return (
        "<svg viewBox='0 0 400 160' role='img' aria-label='Line chart'>"
        "<polyline fill='none' stroke='#3b82f6' stroke-width='2' points='"
        f"{polyline}'/>"
        "</svg>"
    )


def list_chart_renderers() -> MutableMapping[str, ChartRenderer]:
    """Return a snapshot of the current renderer registry."""

    return dict(_RENDERERS)


def reset_chart_renderers(include_defaults: bool = True) -> None:
    """Clear the registry and optionally reinstall built-in renderers."""

    _RENDERERS.clear()
    if include_defaults:
        _RENDERERS["line"] = _render_line


__all__ = [
    "register_chart_renderer",
    "render_route_charts",
    "get_chart_renderer",
    "list_chart_renderers",
    "reset_chart_renderers",
]
