from __future__ import annotations

import datetime as dt
from pathlib import Path

import pyarrow as pa
import pytest

import duckdb

from webbed_duck.config import Config, load_config
from webbed_duck.core.compiler import compile_routes
from webbed_duck.core.incremental import run_incremental
from webbed_duck.core.local import run_route
from webbed_duck.core.routes import load_compiled_routes
from webbed_duck.server.app import create_app

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    TestClient = None  # type: ignore


def _write_route(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "route.sql.md"
    path.write_text(content, encoding="utf-8")
    return path


def _make_config(storage_root: Path) -> Config:
    config = load_config(None)
    config.server.storage_root = storage_root
    return config


ROUTE_TEMPLATE = """
+++
id = "hello"
path = "/hello"
[params.name]
type = "str"
required = false
default = "world"

[overrides]
key_columns = ["greeting"]
allowed = ["note"]

[append]
columns = ["greeting", "note", "created_at"]
+++

```sql
SELECT
  'Hello, ' || {{name}} || '!' AS greeting,
  'note from base' AS note,
  CURRENT_DATE AS created_at;
```
"""


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_overrides_and_append(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    build_dir = tmp_path / "build"
    storage_root = tmp_path / "storage"
    src_dir.mkdir()
    _write_route(src_dir, ROUTE_TEMPLATE)
    compile_routes(src_dir, build_dir)
    routes = load_compiled_routes(build_dir)
    config = _make_config(storage_root)
    app = create_app(routes, config)
    client = TestClient(app)

    response = client.post(
        "/routes/hello/overrides",
        json={"column": "note", "key": {"greeting": "Hello, world!"}, "value": "annotated"},
    )
    assert response.status_code == 200
    payload = response.json()["override"]
    assert payload["column"] == "note"

    data_response = client.get("/hello")
    data = data_response.json()
    assert data_response.status_code == 200
    assert data["rows"][0]["note"] == "annotated"

    append = client.post(
        "/routes/hello/append",
        json={"greeting": "Hello, world!", "note": "annotated", "created_at": "2025-01-01"},
    )
    assert append.status_code == 200
    append_path = Path(append.json()["path"])
    assert append_path.exists()


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_schema_endpoint(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    build_dir = tmp_path / "build"
    src_dir.mkdir()
    _write_route(src_dir, ROUTE_TEMPLATE)
    compile_routes(src_dir, build_dir)
    routes = load_compiled_routes(build_dir)
    config = _make_config(tmp_path / "storage")
    app = create_app(routes, config)
    client = TestClient(app)

    response = client.get("/routes/hello/schema")
    assert response.status_code == 200
    payload = response.json()
    assert payload["route_id"] == "hello"
    assert any(field["name"] == "greeting" for field in payload["schema"])
    assert any(item["name"] == "name" for item in payload["form"])


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_routes_endpoint_reports_metrics(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    build_dir = tmp_path / "build"
    src_dir.mkdir()
    _write_route(src_dir, ROUTE_TEMPLATE)
    compile_routes(src_dir, build_dir)
    routes = load_compiled_routes(build_dir)
    config = _make_config(tmp_path / "storage")
    app = create_app(routes, config)
    client = TestClient(app)

    client.get("/hello")
    response = client.get("/routes")
    assert response.status_code == 200
    data = response.json()
    assert "folders" in data
    route_entry = next(item for item in data["routes"] if item["id"] == "hello")
    assert route_entry["metrics"]["hits"] >= 1
    assert route_entry["metrics"]["rows"] >= 1


def test_run_route_local(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    build_dir = tmp_path / "build"
    src_dir.mkdir()
    _write_route(src_dir, ROUTE_TEMPLATE)
    compile_routes(src_dir, build_dir)

    table = run_route("hello", params={"name": "Duck"}, build_dir=build_dir, config=_make_config(tmp_path / "storage"))
    assert isinstance(table, pa.Table)
    assert table.column("greeting")[0].as_py() == "Hello, Duck!"


def test_run_incremental_tracks_progress(tmp_path: Path) -> None:
    incremental_route = """
+++
id = "by_date"
path = "/by_date"
[params.day]
type = "str"
required = true
+++

```sql
SELECT {{day}} AS day_value;
```
"""
    src_dir = tmp_path / "src"
    build_dir = tmp_path / "build"
    storage_root = tmp_path / "storage"
    src_dir.mkdir()
    _write_route(src_dir, incremental_route)
    compile_routes(src_dir, build_dir)

    config = _make_config(storage_root)
    start = dt.date(2025, 1, 1)
    end = dt.date(2025, 1, 3)
    results = run_incremental(
        "by_date",
        cursor_param="day",
        start=start,
        end=end,
        config=config,
        build_dir=build_dir,
    )
    assert len(results) == 3
    checkpoint_path = storage_root / "runtime" / "checkpoints.duckdb"
    assert checkpoint_path.exists()
    conn = duckdb.connect(checkpoint_path)
    try:
        row = conn.execute(
            "SELECT cursor_value FROM checkpoints WHERE route_id = ? AND cursor_param = ?",
            ("by_date", "day"),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None and row[0] == "2025-01-03"

ROUTE_REPORTS_INDEX = (
    "+++\n"
    "id = \"reports_index\"\n"
    "path = \"/reports\"\n"
    "+++\n\n"
    "```sql\nSELECT 'index' AS label;\n```\n"
)

ROUTE_REPORTS_DAILY_SUMMARY = (
    "+++\n"
    "id = \"reports_daily_summary\"\n"
    "path = \"/reports/daily/summary\"\n"
    "+++\n\n"
    "```sql\nSELECT 'summary' AS label UNION ALL SELECT 'summary-2' AS label;\n```\n"
)

ROUTE_REPORTS_DAILY_DETAIL = (
    "+++\n"
    "id = \"reports_daily_detail\"\n"
    "path = \"/reports/daily/detail\"\n"
    "+++\n\n"
    "```sql\nSELECT 'detail' AS label;\n```\n"
)


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_routes_endpoint_folder_aggregation(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    build_dir = tmp_path / "build"
    src_dir.mkdir()
    (src_dir / "index.sql.md").write_text(ROUTE_REPORTS_INDEX, encoding="utf-8")
    (src_dir / "summary.sql.md").write_text(ROUTE_REPORTS_DAILY_SUMMARY, encoding="utf-8")
    (src_dir / "detail.sql.md").write_text(ROUTE_REPORTS_DAILY_DETAIL, encoding="utf-8")
    compile_routes(src_dir, build_dir)
    routes = load_compiled_routes(build_dir)
    config = _make_config(tmp_path / "storage")
    app = create_app(routes, config)
    client = TestClient(app)

    client.get("/reports")
    client.get("/reports/daily/summary")
    client.get("/reports/daily/detail")

    response = client.get("/routes", params={"folder": "/reports"})
    assert response.status_code == 200
    data = response.json()
    assert data["folder"] == "/reports"
    route_ids = {item["id"] for item in data["routes"]}
    assert "reports_index" in route_ids
    folders = {item["path"]: item for item in data["folders"]}
    assert "/reports/daily" in folders
    summary = folders["/reports/daily"]
    assert summary["route_count"] == 2
    assert summary["hits"] >= 2
    assert summary["rows"] >= 3
