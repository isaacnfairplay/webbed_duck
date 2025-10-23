from __future__ import annotations

from pathlib import Path

import pytest

from webbed_duck.core.compiler import RouteCompilationError, compile_route_file, compile_routes
from webbed_duck.core.routes import load_compiled_routes
from webbed_duck.server.app import create_app
from webbed_duck.config import load_config

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:  # pragma: no cover - allow import error during type checking
    TestClient = None  # type: ignore


def write_route(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "sample.sql.md"
    path.write_text(content, encoding="utf-8")
    return path


def test_compile_route(tmp_path: Path) -> None:
    route_text = (
        "+++\n"
        "id = \"sample\"\n"
        "path = \"/sample\"\n"
        "[params.name]\n"
        "type = \"str\"\n"
        "required = true\n"
        "+++\n\n"
        "```sql\nSELECT {{name}} as value\n```\n"
    )
    route_path = write_route(tmp_path, route_text)
    definition = compile_route_file(route_path)
    assert definition.param_order == ["name"]
    assert definition.prepared_sql == "SELECT ? as value"

    build_dir = tmp_path / "build"
    compiled = compile_routes(tmp_path, build_dir)
    assert compiled[0].id == "sample"

    loaded = load_compiled_routes(build_dir)
    assert loaded[0].id == "sample"


def test_compile_fails_without_sql(tmp_path: Path) -> None:
    route_text = "+++\nid = \"broken\"\npath = \"/broken\"\n+++\n"
    path = write_route(tmp_path, route_text)
    with pytest.raises(RouteCompilationError):
        compile_route_file(path)


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_server_returns_rows(tmp_path: Path) -> None:
    route_text = (
        "+++\n"
        "id = \"hello\"\n"
        "path = \"/hello\"\n"
        "[params.name]\n"
        "type = \"str\"\n"
        "required = false\n"
        "default = \"world\"\n"
        "+++\n\n"
        "```sql\nSELECT 'Hello, ' || {{name}} || '!' AS greeting\n```\n"
    )
    src_dir = tmp_path / "routes"
    src_dir.mkdir()
    write_route(src_dir, route_text)
    build_dir = tmp_path / "build"
    compile_routes(src_dir, build_dir)
    routes = load_compiled_routes(build_dir)
    app = create_app(routes, load_config(None))
    client = TestClient(app)

    response = client.get("/hello", params={"name": "DuckDB"})
    data = response.json()
    assert response.status_code == 200
    assert data["rows"][0]["greeting"] == "Hello, DuckDB!"

    html_response = client.get("/hello", params={"name": "DuckDB", "format": "html_t"})
    assert html_response.status_code == 200
    assert "Hello, DuckDB!" in html_response.text

    cards_response = client.get("/hello", params={"name": "DuckDB", "format": "html_c"})
    assert cards_response.status_code == 200
    assert "Hello, DuckDB!" in cards_response.text

    arrow_response = client.get("/hello", params={"name": "DuckDB", "format": "arrow", "limit": 1})
    assert arrow_response.status_code == 200
    assert arrow_response.headers["content-type"].startswith("application/vnd.apache.arrow.stream")

    feed_response = client.get("/hello", params={"name": "DuckDB", "format": "feed"})
    assert feed_response.status_code == 200
    assert "<section" in feed_response.text

    analytics = client.get("/routes")
    assert analytics.status_code == 200
    payload = analytics.json()
    assert payload["routes"][0]["id"] == "hello"
