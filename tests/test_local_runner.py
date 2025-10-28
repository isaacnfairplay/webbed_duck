from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pytest

from tests.conftest import write_sidecar_route
from webbed_duck.config import load_config
from webbed_duck.core.compiler import compile_routes
from webbed_duck.core.local import LocalRouteRunner, RouteNotFoundError, run_route
from webbed_duck.core.routes import load_compiled_routes

ROUTE_TEXT = """+++
id = "hello"
path = "/hello"
[params.name]
type = "str"
required = false
default = "World"
[cache]
order_by = ["greeting"]
+++

```sql
SELECT 'Hello, ' || {{name}} || '!' AS greeting
```
"""


def _build_runner(tmp_path: Path) -> LocalRouteRunner:
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
    return LocalRouteRunner(routes=routes, config=config)


def test_local_route_runner_returns_arrow_table(tmp_path: Path) -> None:
    runner = _build_runner(tmp_path)

    result = runner.run("hello")

    assert isinstance(result, pa.Table)
    assert result.to_pydict()["greeting"] == ["Hello, World!"]


def test_local_route_runner_supports_records(tmp_path: Path) -> None:
    runner = _build_runner(tmp_path)

    result = runner.run("hello", params={"name": "Ada"}, format="records")

    assert result == [{"greeting": "Hello, Ada!"}]


def test_local_route_runner_rejects_unknown_format(tmp_path: Path) -> None:
    runner = _build_runner(tmp_path)

    with pytest.raises(ValueError):
        runner.run("hello", format="xml")


def test_run_route_preserves_existing_entrypoint(tmp_path: Path) -> None:
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

    result = run_route("hello", routes=routes, config=config)

    assert isinstance(result, pa.Table)
    assert result.column("greeting").to_pylist() == ["Hello, World!"]


def test_local_route_runner_unknown_route(tmp_path: Path) -> None:
    runner = _build_runner(tmp_path)

    with pytest.raises(RouteNotFoundError):
        runner.run("missing")

