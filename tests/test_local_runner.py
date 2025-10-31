from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pytest

from tests.conftest import write_sidecar_route
from webbed_duck.config import load_config
from webbed_duck.core.compiler import compile_routes
from webbed_duck.core.local import LocalRouteRunner, RouteNotFoundError, run_route
from webbed_duck.core.routes import load_compiled_routes
from webbed_duck.server.execution import RouteExecutionError
from webbed_duck.server.overlay import OverlayStore, compute_row_key_from_values

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


ROUTE_WITH_OVERRIDES = """+++
id = "overridable"
path = "/overridable"

[cache]
order_by = ["id"]

[overrides]
key_columns = ["id"]
allowed = ["note"]
+++

```sql
SELECT 1 AS id, 'baseline' AS note
```
"""


ROUTE_WITH_PAGINATION = """+++
id = "paginated"
path = "/paginated"

[cache]
order_by = ["id"]
+++

```sql
SELECT *
FROM (VALUES (1), (2), (3), (4)) AS t(id)
ORDER BY id
```
"""


def _build_runner(tmp_path: Path, *, route_text: str = ROUTE_TEXT, stem: str = "hello") -> LocalRouteRunner:
    src_dir = tmp_path / "src"
    build_dir = tmp_path / "build"
    storage_root = tmp_path / "storage"
    src_dir.mkdir()
    storage_root.mkdir()
    write_sidecar_route(src_dir, stem, route_text)
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


def test_local_route_runner_wraps_execution_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = _build_runner(tmp_path)

    class _ExplodingExecutor:
        def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            pass

        def execute_relation(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise RouteExecutionError("boom")

    monkeypatch.setattr("webbed_duck.core.local.RouteExecutor", _ExplodingExecutor)

    with pytest.raises(ValueError) as excinfo:
        runner.run("hello")

    assert "boom" in str(excinfo.value)


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


def test_local_route_runner_refreshes_overrides(tmp_path: Path) -> None:
    runner = _build_runner(tmp_path, route_text=ROUTE_WITH_OVERRIDES, stem="overridable")

    initial = runner.run("overridable", format="records")
    assert initial == [{"id": 1, "note": "baseline"}]

    storage_root = tmp_path / "storage"
    overlay_store = OverlayStore(storage_root)
    row_key = compute_row_key_from_values({"id": 1}, ["id"])
    overlay_store.upsert(
        route_id="overridable",
        row_key=row_key,
        column="note",
        value="patched",
    )

    refreshed = runner.run("overridable", format="records")
    assert refreshed == [{"id": 1, "note": "patched"}]


def test_local_route_runner_applies_offset_and_limit(tmp_path: Path) -> None:
    runner = _build_runner(tmp_path, route_text=ROUTE_WITH_PAGINATION, stem="paginated")

    result = runner.run("paginated", format="records", offset=1, limit=2)

    assert result == [{"id": 2}, {"id": 3}]


def test_local_route_runner_sanitizes_negative_pagination(tmp_path: Path) -> None:
    runner = _build_runner(tmp_path, route_text=ROUTE_WITH_PAGINATION, stem="paginated")

    result = runner.run("paginated", format="records", offset=-4, limit=-1)

    assert result == []

