"""Tests for the plugin registries used by webbed_duck."""

from __future__ import annotations

import pytest
import pyarrow as pa

import webbed_duck.plugins.assets as assets
import webbed_duck.plugins.charts as charts
from webbed_duck.plugins.assets import register_image_getter, resolve_image
from webbed_duck.plugins.charts import register_chart_renderer, render_route_charts


@pytest.fixture()
def asset_registry(monkeypatch):
    """Reset the asset registry to the static fallback for each test."""

    original = dict(getattr(assets, "_REGISTRY", {}))
    base = {"static_fallback": assets.static_fallback}
    monkeypatch.setattr(assets, "_REGISTRY", base.copy(), raising=False)
    try:
        yield assets._REGISTRY
    finally:
        monkeypatch.setattr(assets, "_REGISTRY", original, raising=False)


@pytest.fixture()
def chart_registry(monkeypatch):
    """Reset the chart renderer registry to only include the built-in line chart."""

    original = dict(getattr(charts, "_RENDERERS", {}))
    base = {"line": charts._render_line}
    monkeypatch.setattr(charts, "_RENDERERS", base.copy(), raising=False)
    try:
        yield charts._RENDERERS
    finally:
        monkeypatch.setattr(charts, "_RENDERERS", original, raising=False)


def test_resolve_image_uses_registered_getter(asset_registry):
    calls: list[tuple[str, str]] = []

    @register_image_getter("cdn")
    def _cdn(name: str, route_id: str) -> str:
        calls.append((name, route_id))
        return f"https://cdn.example/{route_id}/{name}"

    result = resolve_image("logo.png", "routes/home", "cdn")

    assert result == "https://cdn.example/routes/home/logo.png"
    assert calls == [("logo.png", "routes/home")]


def test_resolve_image_falls_back_to_static(asset_registry):
    assert resolve_image("hero.jpg", "routes/about", "unknown") == "/static/hero.jpg"


def test_render_route_charts_custom_renderer(chart_registry):
    @register_chart_renderer("custom")
    def _custom_renderer(table: pa.Table, spec):
        assert spec["title"] == "Demo"
        return "<div>demo</div>"

    table = pa.table({"value": [1, 2, 3]})
    specs = [{"type": "custom", "id": "demo", "title": "Demo"}]

    rendered = render_route_charts(table, specs)

    assert rendered == [{"id": "demo", "html": "<div>demo</div>"}]


def test_render_route_charts_skips_unknown_types(chart_registry):
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


def test_render_route_charts_builtin_line_renderer(chart_registry):
    table = pa.table({"value": [10, 20, 30]})
    specs = [{"type": "line", "id": "sparkline", "y": "value"}]

    rendered = render_route_charts(table, specs)

    assert rendered and rendered[0]["id"] == "sparkline"
    assert "<polyline" in rendered[0]["html"]
    assert "role='img'" in rendered[0]["html"]


def test_render_route_charts_reports_renderer_failure(chart_registry):
    @register_chart_renderer("boom")
    def _boom(table: pa.Table, spec):
        raise RuntimeError("kaboom")

    table = pa.table({"value": [1, 2]})
    specs = [{"type": "boom", "id": "broken"}]

    rendered = render_route_charts(table, specs)

    assert rendered == [{"id": "broken", "html": "<pre>Chart 'broken' failed: kaboom</pre>"}]


def test_render_line_renderer_handles_missing_column(chart_registry):
    table = pa.table({"other": [1, 2, 3]})
    specs = [{"type": "line", "id": "missing", "y": "value"}]

    rendered = render_route_charts(table, specs)

    assert rendered == [
        {
            "id": "missing",
            "html": "<svg viewBox='0 0 400 160'><text x='8' y='80'>Unknown y column: value</text></svg>",
        }
    ]


def test_render_line_renderer_handles_non_numeric_data(chart_registry):
    table = pa.table({"value": ["a", "b"]})
    specs = [{"type": "line", "id": "letters", "y": "value"}]

    rendered = render_route_charts(table, specs)

    assert rendered == [
        {
            "id": "letters",
            "html": "<svg viewBox='0 0 400 160'><text x='8' y='80'>Non-numeric data</text></svg>",
        }
    ]
