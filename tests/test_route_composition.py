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


def _write_pair(base: Path, stem: str, toml: str, sql: str) -> None:
    (base / f"{stem}.toml").write_text(toml, encoding="utf-8")
    (base / f"{stem}.sql").write_text(sql, encoding="utf-8")


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_route_dependency_relation_mode(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    build = tmp_path / "build"
    storage = tmp_path / "storage"
    storage.mkdir()

    _write_pair(
        src,
        "child",
        """
id = "child"
path = "/child"
title = "child"
cache_mode = "passthrough"
""".strip(),
        """
SELECT 1 AS value
""".strip(),
    )

    _write_pair(
        src,
        "parent",
        """
id = "parent"
path = "/parent"
cache_mode = "passthrough"

[[uses]]
alias = "child_view"
call = "child"
mode = "relation"
""".strip(),
        """
SELECT * FROM child_view
""".strip(),
    )

    compile_routes(src, build)
    routes = load_compiled_routes(build)
    config = load_config(None)
    config.server.storage_root = storage
    app = create_app(routes, config)
    client = TestClient(app)

    response = client.get("/parent", params={"format": "json"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["rows"] == [{"value": 1}]


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_route_dependency_parquet_mode(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    build = tmp_path / "build"
    storage = tmp_path / "storage"
    storage.mkdir()

    _write_pair(
        src,
        "child",
        """
id = "child"
path = "/child"
cache_mode = "materialize"
[cache]
order_by = ["id"]
rows_per_page = 10
""".strip(),
        """
SELECT *
FROM (VALUES (1, 'a'), (2, 'b')) AS t(id, label)
""".strip(),
    )

    _write_pair(
        src,
        "parent",
        """
id = "parent"
path = "/parent"
cache_mode = "passthrough"

[[uses]]
alias = "child_cache"
call = "child"
mode = "parquet_path"
""".strip(),
        """
SELECT * FROM child_cache ORDER BY id
""".strip(),
    )

    compile_routes(src, build)
    routes = load_compiled_routes(build)
    config = load_config(None)
    config.server.storage_root = storage
    app = create_app(routes, config)
    client = TestClient(app)

    response = client.get("/parent", params={"format": "json"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["rows"] == [{"id": 1, "label": "a"}, {"id": 2, "label": "b"}]

    cache_root = storage / "cache"
    child_dirs = list(cache_root.glob("child/*"))
    assert child_dirs, "expected child cache entry to be materialized"
    parquet_files = list(child_dirs[0].glob("page-*.parquet"))
    assert parquet_files, "parquet_path dependency should produce parquet artifacts"


@pytest.mark.skipif(TestClient is None, reason="fastapi is not available")
def test_parquet_dependency_handles_empty_results(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    build = tmp_path / "build"
    storage = tmp_path / "storage"
    storage.mkdir()

    _write_pair(
        src,
        "empty_child",
        """
id = "empty_child"
path = "/empty_child"
cache_mode = "materialize"

[cache]
order_by = ["id"]
rows_per_page = 5
""".strip(),
        """
SELECT id, label
FROM (VALUES (1, 'a')) AS t(id, label)
WHERE 1 = 0
""".strip(),
    )

    _write_pair(
        src,
        "parent_empty",
        """
id = "parent_empty"
path = "/parent_empty"
cache_mode = "passthrough"

[[uses]]
alias = "empty_alias"
call = "empty_child"
mode = "parquet_path"
""".strip(),
        """
SELECT * FROM empty_alias
ORDER BY id
""".strip(),
    )

    compile_routes(src, build)
    routes = load_compiled_routes(build)
    config = load_config(None)
    config.server.storage_root = storage
    app = create_app(routes, config)
    client = TestClient(app)

    response = client.get("/parent_empty", params={"format": "json"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["rows"] == []
    assert payload["row_count"] == 0
