from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover - optional dependency
    TestClient = None  # type: ignore

from webbed_duck.config import load_config
from webbed_duck.core.compiler import compile_routes
from webbed_duck.core.routes import load_compiled_routes
from webbed_duck.server.app import create_app
from webbed_duck.static.chartjs import CHARTJS_FILENAME, CHARTJS_VERSION


def _write_pair(root: Path, stem: str, toml: str, sql: str) -> None:
    (root / f"{stem}.toml").write_text(toml, encoding="utf-8")
    (root / f"{stem}.sql").write_text(sql, encoding="utf-8")


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_html_table_renders_filters_and_rpc_metadata(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    routes = load_compiled_routes(repo_root / "routes_build")
    config = load_config(None)
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    config.server.storage_root = storage_root
    app = create_app(routes, config)
    client = TestClient(app)

    response = client.get(
        "/hello",
        params={"format": "html_t", "limit": "1", "name": "Filters"},
    )
    assert response.status_code == 200
    assert response.headers["x-total-rows"] == "1"
    assert response.headers["x-offset"] == "0"
    assert response.headers["x-limit"] == "1"
    assert "params-form" in response.text
    assert re.search(r"<label[^>]*>\s*Name\s*</label>", response.text)
    assert re.search(
        r"<input[^>]+name=['\"]name['\"][^>]+value=['\"]Filters['\"]",
        response.text,
    )
    assert re.search(
        r"<input[^>]+type=['\"]hidden['\"][^>]+name=['\"]limit['\"][^>]+value=['\"]1['\"]",
        response.text,
    )

    match = re.search(
        r"<script type='application/json' id='wd-rpc-config'>(?P<data>.+?)</script>",
        response.text,
        re.DOTALL,
    )
    assert match, "RPC payload script missing from html_t response"
    payload = json.loads(match.group("data"))
    assert payload["endpoint"].endswith("format=arrow_rpc")
    assert payload["limit"] == 1
    assert payload["offset"] == 0
    assert payload["total_rows"] == 1


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_html_cards_include_filters_and_rpc_metadata(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    routes = load_compiled_routes(repo_root / "routes_build")
    config = load_config(None)
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    config.server.storage_root = storage_root
    app = create_app(routes, config)
    client = TestClient(app)

    response = client.get(
        "/hello",
        params={"format": "html_c", "limit": "1", "name": "Crew"},
    )
    assert response.status_code == 200
    assert response.headers["x-total-rows"] == "1"
    assert response.headers["x-offset"] == "0"
    assert response.headers["x-limit"] == "1"
    assert "params-form" in response.text
    assert re.search(r"<label[^>]*>\s*Name\s*</label>", response.text)
    assert re.search(
        r"<input[^>]+name=['\"]name['\"][^>]+value=['\"]Crew['\"]",
        response.text,
    )

    match = re.search(
        r"<script type='application/json' id='wd-rpc-config'>(?P<data>.+?)</script>",
        response.text,
        re.DOTALL,
    )
    assert match, "RPC payload script missing from html_c response"
    payload = json.loads(match.group("data"))
    assert payload["endpoint"].endswith("format=arrow_rpc")
    assert payload["limit"] == 1
    assert payload["offset"] == 0
    assert payload["total_rows"] == 1


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_chart_js_format_supports_full_and_embed(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    routes = load_compiled_routes(repo_root / "routes_build")
    config = load_config(None)
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    vendor_dir = storage_root / "static" / "vendor" / "chartjs"
    vendor_dir.mkdir(parents=True)
    (vendor_dir / CHARTJS_FILENAME).write_text("window.Chart=function(){};")
    config.server.storage_root = storage_root
    app = create_app(routes, config)
    client = TestClient(app)

    response = client.get("/hello", params={"format": "chart_js"})
    assert response.status_code == 200
    assert response.headers["x-total-rows"] == "1"
    assert f"/vendor/{CHARTJS_FILENAME}?v={CHARTJS_VERSION}" in response.text
    assert "data-wd-chart='greeting_length-config'" in response.text

    asset = client.get(f"/vendor/{CHARTJS_FILENAME}")
    assert asset.status_code == 200
    assert "window.Chart" in asset.text

    embed = client.get("/hello", params={"format": "chart_js", "embed": "1"})
    assert embed.status_code == 200
    assert "<!doctype html>" not in embed.text
    assert embed.text.count("<canvas") >= 1


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_multi_value_query_params_preserve_all_selected_options(tmp_path: Path) -> None:
    src = tmp_path / "src"
    build = tmp_path / "build"
    src.mkdir()
    build.mkdir()
    _write_pair(
        src,
        "multi_filter",
        """
id = "multi_filter"
path = "/multi-filter"
default_format = "json"
cache_mode = "passthrough"

[params.category]
type = "str"
required = false
""".strip(),
        """
SELECT
    len($category::TEXT[]) AS value_count,
    $category::TEXT[] AS categories;
""".strip(),
    )

    compile_routes(src, build)
    routes = load_compiled_routes(build)
    config = load_config(None)
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    config.server.storage_root = storage_root
    app = create_app(routes, config)
    client = TestClient(app)

    response = client.get(
        "/multi-filter",
        params=[
            ("category", "alpha"),
            ("category", "beta"),
            ("format", "json"),
        ],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["rows"] == [
        {"value_count": 2, "categories": ["alpha", "beta"]}
    ]
