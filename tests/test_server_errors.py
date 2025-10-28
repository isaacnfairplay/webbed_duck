from __future__ import annotations

import duckdb
import pathlib
import pytest

from webbed_duck.config import load_config
from webbed_duck.core.compiler import compile_routes
from webbed_duck.core.routes import load_compiled_routes
from webbed_duck.server.app import create_app
from webbed_duck.server.execution import RouteExecutor

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    TestClient = None  # type: ignore


def _write_pair(tmp_path: pathlib.Path, stem: str, toml: str, sql: str) -> None:
    (tmp_path / f"{stem}.toml").write_text(toml, encoding="utf-8")
    (tmp_path / f"{stem}.sql").write_text(sql, encoding="utf-8")


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_duckdb_error_surfaces_as_http_500(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    src = tmp_path / "src"
    build = tmp_path / "build"
    src.mkdir()
    build.mkdir()
    _write_pair(
        src,
        "error_route",
        """
id = "error_route"
path = "/error"

[cache]
order_by = ["value"]
""".strip(),
        "SELECT 1 AS value;",
    )
    compile_routes(src, build)
    routes = load_compiled_routes(build)
    config = load_config(None)
    config.server.storage_root = tmp_path / "storage"
    config.server.storage_root.mkdir()
    app = create_app(routes, config)

    error = duckdb.Error("forced failure")

    def raise_duckdb_error(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise error

    monkeypatch.setattr(RouteExecutor, "execute_relation", raise_duckdb_error)

    client = TestClient(app)
    response = client.get("/error", params={"format": "json"})
    assert response.status_code == 500
    payload = response.json()
    assert payload["detail"]["code"] == "duckdb_error"
    assert "forced failure" in payload["detail"]["message"]
