from pathlib import Path

import pytest

from tests.conftest import write_sidecar_route
from webbed_duck.config import load_config
from webbed_duck.core.compiler import compile_routes
from webbed_duck.core.routes import load_compiled_routes
from webbed_duck.server.app import create_app

try:  # pragma: no cover - optional dependency guard
    from fastapi.testclient import TestClient
except ModuleNotFoundError:  # pragma: no cover
    TestClient = None  # type: ignore


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_append_route_requires_columns(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    build = tmp_path / "build"

    write_sidecar_route(
        src,
        "append_missing_columns",
        (
            "+++\n"
            "id = \"append_missing_columns\"\n"
            "path = \"/append_missing_columns\"\n"
            "cache_mode = \"passthrough\"\n"
            "[append]\n"
            "destination = \"logs/out.csv\"\n"
            "+++\n\n"
            "```sql\nSELECT 1 AS value\n```\n"
        ),
    )

    compile_routes(src, build)
    routes = load_compiled_routes(build)

    config = load_config(None)
    config.server.storage_root = tmp_path / "storage"
    config.server.storage_root.mkdir()
    app = create_app(routes, config)
    client = TestClient(app)

    response = client.post(
        "/routes/append_missing_columns/append",
        json={"value": 1},
    )

    assert response.status_code == 500
    payload = response.json()
    assert payload["detail"]["code"] == "append_misconfigured"
    assert "declare columns" in payload["detail"]["message"]


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_append_route_rejects_escape_destination(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    build = tmp_path / "build"

    write_sidecar_route(
        src,
        "append_escape",
        (
            "+++\n"
            "id = \"append_escape\"\n"
            "path = \"/append_escape\"\n"
            "cache_mode = \"passthrough\"\n"
            "[append]\n"
            "columns = [\"value\"]\n"
            "destination = \"../escape.csv\"\n"
            "+++\n\n"
            "```sql\nSELECT 1 AS value\n```\n"
        ),
    )

    compile_routes(src, build)
    routes = load_compiled_routes(build)

    config = load_config(None)
    config.server.storage_root = tmp_path / "storage"
    config.server.storage_root.mkdir()
    app = create_app(routes, config)
    client = TestClient(app)

    response = client.post(
        "/routes/append_escape/append",
        json={"value": 1},
    )

    assert response.status_code == 500
    payload = response.json()
    assert payload["detail"]["code"] == "append_misconfigured"
    message = payload["detail"]["message"].lower()
    assert "runtime" in message and "append" in message


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_append_route_missing_metadata_returns_404(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    build = tmp_path / "build"

    write_sidecar_route(
        src,
        "no_append",
        (
            "+++\n"
            "id = \"no_append\"\n"
            "path = \"/no_append\"\n"
            "cache_mode = \"passthrough\"\n"
            "+++\n\n"
            "```sql\nSELECT 1 AS value\n```\n"
        ),
    )

    compile_routes(src, build)
    routes = load_compiled_routes(build)

    config = load_config(None)
    config.server.storage_root = tmp_path / "storage"
    app = create_app(routes, config)
    client = TestClient(app)

    response = client.post(
        "/routes/no_append/append",
        json={"value": 1},
    )

    assert response.status_code == 404
    payload = response.json()
    assert payload["detail"]["code"] == "append_not_configured"
