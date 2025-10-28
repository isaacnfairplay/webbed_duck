from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import write_sidecar_route
from webbed_duck.config import load_config
from webbed_duck.core.compiler import compile_routes
from webbed_duck.core.routes import (
    ParameterSpec,
    ParameterType,
    RouteDefinition,
    load_compiled_routes,
)
from webbed_duck.server import app as server_app
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
    write_sidecar_route(src_dir, "hello", ROUTE_TEXT)
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


def _sample_route() -> RouteDefinition:
    return RouteDefinition(
        id="hello",
        path="/hello",
        methods=("GET",),
        raw_sql="SELECT 1",
        prepared_sql="SELECT 1",
        param_order=("name",),
        params=(
            ParameterSpec(name="name", type=ParameterType.STRING, required=False, default="World"),
        ),
        default_format="json",
    )


def test_resolve_reference_alias_supports_target_key() -> None:
    route = _sample_route()
    payload = {"target": " local:hello   "}

    request = server_app._build_local_reference_request(payload, [route])

    assert request.route is route
    assert request.format == "json"


def test_resolve_reference_alias_rejects_blank_string() -> None:
    route = _sample_route()

    with pytest.raises(server_app.HTTPException) as excinfo:
        server_app._build_local_reference_request({"reference": "   "}, [route])

    detail = excinfo.value.detail
    assert detail["code"] == "invalid_parameter"
    assert "non-empty" in detail["message"]


def test_parse_local_reference_merges_columns() -> None:
    parsed = server_app._parse_local_reference(
        "local:hello?column=one&columns=two, three ,,&format=JSON&limit=5&offset=2&extra=value"
    )

    assert isinstance(parsed, server_app.ParsedLocalReference)
    assert parsed.route_id == "hello"
    assert parsed.params == {"extra": "value"}
    assert parsed.columns == ("one", "two", "three")
    assert parsed.format == "JSON"
    assert parsed.limit == "5"
    assert parsed.offset == "2"


def test_parse_local_reference_requires_local_prefix() -> None:
    with pytest.raises(ValueError):
        server_app._parse_local_reference("hello")

    with pytest.raises(ValueError):
        server_app._parse_local_reference("local:")
