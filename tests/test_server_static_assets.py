from __future__ import annotations

from pathlib import Path

import pytest

from webbed_duck.config import load_config
from webbed_duck.core.routes import RouteDefinition
from webbed_duck.server.app import create_app

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:  # pragma: no cover - optional dependency during typing
    TestClient = None  # type: ignore


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_package_assets_are_served(tmp_path: Path) -> None:
    storage_root = tmp_path / "storage"
    storage_root.mkdir()

    config = load_config(None)
    config.server.storage_root = storage_root

    route = RouteDefinition(
        id="asset-check",
        path="/asset-check",
        methods=("GET",),
        raw_sql="SELECT 1 AS value",
        prepared_sql="SELECT 1 AS value",
        param_order=(),
        params=(),
    )

    app = create_app([route], config)
    client = TestClient(app)

    css_response = client.get("/assets/wd/layout.css")
    assert css_response.status_code == 200
    assert ".wd-shell" in css_response.text

    js_response = client.get("/assets/wd/multi_select.js")
    assert js_response.status_code == 200
    assert "wd-multi-select" in js_response.text
