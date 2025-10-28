from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import write_sidecar_route
from webbed_duck.config import load_config
from webbed_duck.core.compiler import compile_routes
from webbed_duck.core.routes import RouteDefinition, load_compiled_routes
from webbed_duck.server.cache import CacheStore
from webbed_duck.server.execution import RouteExecutionError, RouteExecutor


def _compile(base: Path) -> list[RouteDefinition]:
    src = base / "src"
    build = base / "build"
    compile_routes(src, build)
    return load_compiled_routes(build)


def _make_executor(routes: list[RouteDefinition], storage_root: Path) -> RouteExecutor:
    config = load_config(None)
    config.server.storage_root = storage_root
    store = CacheStore(storage_root)
    return RouteExecutor({route.id: route for route in routes}, cache_store=store, config=config)


def test_dependency_missing_route_raises(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    write_sidecar_route(
        src,
        "orphan",
        (
            "+++\n"
            "id = \"orphan\"\n"
            "path = \"/orphan\"\n"
            "cache_mode = \"passthrough\"\n"
            "[[uses]]\n"
            "alias = \"ghost\"\n"
            "call = \"missing_child\"\n"
            "mode = \"relation\"\n"
            "+++\n\n"
            "```sql\nSELECT 1 AS value\n```\n"
        ),
    )

    routes = _compile(tmp_path)
    executor = _make_executor(routes, tmp_path / "storage")
    route = routes[0]

    with pytest.raises(RouteExecutionError) as excinfo:
        executor.execute_relation(route, params={})

    assert "references unknown dependency" in str(excinfo.value)
    assert "missing_child" in str(excinfo.value)


def test_dependency_unsupported_mode(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    write_sidecar_route(
        src,
        "child",
        (
            "+++\n"
            "id = \"child\"\n"
            "path = \"/child\"\n"
            "cache_mode = \"passthrough\"\n"
            "+++\n\n"
            "```sql\nSELECT 'alpha' AS label\n```\n"
        ),
    )
    write_sidecar_route(
        src,
        "parent",
        (
            "+++\n"
            "id = \"parent\"\n"
            "path = \"/parent\"\n"
            "cache_mode = \"passthrough\"\n"
            "[[uses]]\n"
            "alias = \"child_alias\"\n"
            "call = \"child\"\n"
            "mode = \"csv\"\n"
            "+++\n\n"
            "```sql\nSELECT 1 AS value\n```\n"
        ),
    )

    routes = _compile(tmp_path)
    executor = _make_executor(routes, tmp_path / "storage")
    parent = next(route for route in routes if route.id == "parent")

    with pytest.raises(RouteExecutionError) as excinfo:
        executor.execute_relation(parent, params={})

    message = str(excinfo.value)
    assert "unsupported mode" in message
    assert "csv" in message


def test_dependency_argument_forwarding(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    write_sidecar_route(
        src,
        "child",
        (
            "+++\n"
            "id = \"child\"\n"
            "path = \"/child\"\n"
            "cache_mode = \"passthrough\"\n"
            "[params.category]\n"
            "type = \"str\"\n"
            "required = true\n"
            "+++\n\n"
            "```sql\n"
            "SELECT * FROM (VALUES ('A', 'alpha'), ('B', 'bravo')) AS t(category, label)\n"
            "WHERE category = $category\n"
            "ORDER BY label\n"
            "```\n"
        ),
    )
    write_sidecar_route(
        src,
        "parent",
        (
            "+++\n"
            "id = \"parent\"\n"
            "path = \"/parent\"\n"
            "cache_mode = \"passthrough\"\n"
            "[params.category]\n"
            "type = \"str\"\n"
            "required = true\n"
            "[[uses]]\n"
            "alias = \"child_view\"\n"
            "call = \"child\"\n"
            "mode = \"relation\"\n"
            "[uses.args]\n"
            "category = \"category\"\n"
            "+++\n\n"
            "```sql\nSELECT * FROM child_view\n```\n"
        ),
    )

    routes = _compile(tmp_path)
    executor = _make_executor(routes, tmp_path / "storage")
    parent = next(route for route in routes if route.id == "parent")

    result = executor.execute_relation(parent, params={"category": "B"})
    table = result.table.to_pydict()

    assert table == {"category": ["B"], "label": ["bravo"]}

