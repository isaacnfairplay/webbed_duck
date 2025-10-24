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
from webbed_duck.core.routes import load_compiled_routes
from webbed_duck.server.app import create_app


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
