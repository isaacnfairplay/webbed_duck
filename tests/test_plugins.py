"""Tests for the plugin registries used by webbed_duck."""

from __future__ import annotations

import pyarrow as pa

import webbed_duck.plugins.assets as assets
import webbed_duck.plugins.charts as charts
from webbed_duck.plugins.assets import register_image_getter, resolve_image
from webbed_duck.plugins.charts import register_chart_renderer, render_route_charts


def _reset_asset_registry(monkeypatch):
    registry = {"static_fallback": assets.static_fallback}
    monkeypatch.setattr(assets, "_REGISTRY", registry, raising=False)
    return registry


def _reset_chart_registry(monkeypatch):
    registry: dict[str, charts.ChartRenderer] = {}
    monkeypatch.setattr(charts, "_RENDERERS", registry, raising=False)
    return registry


def test_resolve_image_uses_registered_getter(monkeypatch):
    _reset_asset_registry(monkeypatch)

    calls: list[tuple[str, str]] = []

    @register_image_getter("cdn")
    def _cdn(name: str, route_id: str) -> str:
        calls.append((name, route_id))
        return f"https://cdn.example/{route_id}/{name}"

    result = resolve_image("logo.png", "routes/home", "cdn")

    assert result == "https://cdn.example/routes/home/logo.png"
    assert calls == [("logo.png", "routes/home")]


def test_resolve_image_falls_back_to_static(monkeypatch):
    _reset_asset_registry(monkeypatch)

    assert resolve_image("hero.jpg", "routes/about", "unknown") == "/static/hero.jpg"


def test_render_route_charts_custom_renderer(monkeypatch):
    _reset_chart_registry(monkeypatch)

    @register_chart_renderer("custom")
    def _custom_renderer(table: pa.Table, spec):
        assert spec["title"] == "Demo"
        return "<div>demo</div>"

    table = pa.table({"value": [1, 2, 3]})
    specs = [{"type": "custom", "id": "demo", "title": "Demo"}]

    rendered = render_route_charts(table, specs)

    assert rendered == [{"id": "demo", "html": "<div>demo</div>"}]


def test_render_route_charts_skips_unknown_types(monkeypatch):
    _reset_chart_registry(monkeypatch)

    @register_chart_renderer("custom")
    def _custom_renderer(table: pa.Table, spec):
        return "<div>ok</div>"

    table = pa.table({"value": [1, 2, 3]})
    specs = [
        {},
        {"type": "", "id": "ignored"},
        {"type": "missing", "id": "missing"},
        {"type": "custom"},
    ]

    rendered = render_route_charts(table, specs)

    assert rendered == [{"id": "chart_3", "html": "<div>ok</div>"}]


def test_render_route_charts_builtin_line_renderer(monkeypatch):
    _reset_chart_registry(monkeypatch)
    register_chart_renderer("line")(charts._render_line)

    table = pa.table({"value": [10, 20, 30]})
    specs = [{"type": "line", "id": "sparkline", "y": "value"}]

    rendered = render_route_charts(table, specs)

    assert rendered and rendered[0]["id"] == "sparkline"
    assert "<polyline" in rendered[0]["html"]
    assert "role='img'" in rendered[0]["html"]
