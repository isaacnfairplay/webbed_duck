from __future__ import annotations

from pathlib import Path

import pytest

from webbed_duck.config import load_config
from webbed_duck.core.compiler import compile_routes
from webbed_duck.core.routes import load_compiled_routes
from webbed_duck.server.app import create_app

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    TestClient = None  # type: ignore


ROUTE_TEXT = """+++
id = "hello"
path = "/hello"
title = "Local hello"
[params.name]
type = "str"
required = false
default = "World"
allowed_formats = ["json", "csv"]
[cache]
order_by = ["greeting"]
+++

```sql
SELECT
  'Hello, ' || {{name}} || '!' AS greeting,
  'classified' AS secret
```
"""


def _prepare_client(tmp_path: Path) -> TestClient:
    src_dir = tmp_path / "src"
    build_dir = tmp_path / "build"
    storage_root = tmp_path / "storage"
    src_dir.mkdir()
    storage_root.mkdir()
    (src_dir / "hello.sql.md").write_text(ROUTE_TEXT, encoding="utf-8")
    compile_routes(src_dir, build_dir)
    routes = load_compiled_routes(build_dir)
    config = load_config(None)
    config.server.storage_root = storage_root
    config.analytics.enabled = True
    app = create_app(routes, config)
    return TestClient(app)


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_local_resolve_overrides_reference_and_redacts(tmp_path: Path) -> None:
    client = _prepare_client(tmp_path)

    response = client.post(
        "/local/resolve",
        json={
            "reference": "local:hello?name=Egg&column=greeting&limit=1",
            "params": {"name": "Duck"},
            "columns": ["greeting"],
            "format": "json",
            "limit": 2,
            "offset": 0,
            "redact_columns": ["secret"],
            "record_analytics": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["rows"] == [{"greeting": "Hello, Duck!"}]
    assert payload["total_rows"] == 1
    snapshot = client.app.state.analytics.snapshot()
    assert snapshot["hello"]["hits"] >= 1


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_local_resolve_requires_reference(tmp_path: Path) -> None:
    client = _prepare_client(tmp_path)

    response = client.post("/local/resolve", json={})
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "missing_parameter"


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_local_resolve_rejects_non_mapping_params(tmp_path: Path) -> None:
    client = _prepare_client(tmp_path)

    response = client.post(
        "/local/resolve",
        json={"reference": "local:hello", "params": "not-a-mapping"},
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_parameter"
    assert "params" in detail["message"]


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_local_resolve_validates_reference_numbers(tmp_path: Path) -> None:
    client = _prepare_client(tmp_path)

    response = client.post(
        "/local/resolve",
        json={"reference": "local:hello?limit=not-a-number"},
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_parameter"
    assert "integer" in detail["message"]
