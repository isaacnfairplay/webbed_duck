"""Focused coverage for :mod:`webbed_duck.server.execution`."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Iterable

import pytest

from webbed_duck.config import Config
from webbed_duck.core.routes import ParameterSpec, ParameterType, RouteDefinition, RouteUse
from webbed_duck.server.cache import CacheStore
from webbed_duck.server.execution import RouteExecutionError, RouteExecutor

try:  # pragma: no cover - optional dependency in some environments
    import pytest_benchmark  # type: ignore  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover - executed when plugin absent
    _HAVE_BENCHMARK = False
else:  # pragma: no cover - exercised when plugin present
    _HAVE_BENCHMARK = True


def _make_route(
    route_id: str,
    sql: str,
    *,
    params: Iterable[ParameterSpec] | None = None,
    param_order: Iterable[str] | None = None,
    metadata: Mapping[str, object] | None = None,
    uses: Iterable[RouteUse] | None = None,
) -> RouteDefinition:
    metadata_dict: dict[str, object] = {}
    if metadata:
        for key, value in metadata.items():
            if key == "cache" and isinstance(value, Mapping):
                metadata_dict[key] = dict(value)
            else:
                metadata_dict[key] = value
    if "cache" not in metadata_dict:
        metadata_dict["cache"] = {"enabled": False}
    return RouteDefinition(
        id=route_id,
        path=f"/{route_id}",
        methods=["GET"],
        raw_sql=sql,
        prepared_sql=sql,
        param_order=list(param_order or []),
        params=list(params or []),
        metadata=metadata_dict,
        directives=(),
        version=None,
        default_format=None,
        allowed_formats=(),
        preprocess=[],
        postprocess={},
        charts=[],
        assets=None,
        cache_mode="materialize",
        returns="relation",
        uses=tuple(uses or ()),
    )


def _make_executor(routes: Mapping[str, RouteDefinition], storage_root) -> RouteExecutor:
    config = Config()
    config.server.storage_root = storage_root
    store = CacheStore(storage_root)
    return RouteExecutor(routes, cache_store=store, config=config)


@pytest.mark.duckdb
def test_route_executor_applies_cache_invariants(tmp_path):
    metadata = {
        "cache": {
            "order_by": ["value"],
            "rows_per_page": 5,
            "invariant_filters": [{"param": "value", "column": "value"}],
        }
    }
    route = _make_route(
        "invariant_items",
        "SELECT value FROM (VALUES ('alpha'), ('beta'), ('gamma')) AS t(value)",
        params=[ParameterSpec(name="value", type=ParameterType.STRING, required=False)],
        metadata=metadata,
    )

    executor = _make_executor({route.id: route}, tmp_path)

    first = executor.execute_relation(route, {"value": "beta"})
    assert first.used_cache
    assert not first.cache_hit
    assert first.table.column("value").to_pylist() == ["beta"]

    second = executor.execute_relation(route, {"value": "gamma"})
    assert second.used_cache
    assert second.table.column("value").to_pylist() == ["gamma"]

    cache_files = list((tmp_path / "cache").rglob("page-*.parquet"))
    assert cache_files, "expected invariant cache pages to be materialized"


@pytest.mark.duckdb
def test_route_executor_handles_parquet_dependencies(tmp_path):
    child_metadata = {"cache": {"order_by": ["value"], "rows_per_page": 10}}
    child = _make_route(
        "child",
        "SELECT i AS value FROM range(3) AS t(i)",
        metadata=child_metadata,
    )
    parent_use = RouteUse(alias="child_data", call="child", mode="parquet_path")
    parent = _make_route(
        "parent",
        "SELECT SUM(value) AS total FROM child_data",
        uses=[parent_use],
    )
    routes = {child.id: child, parent.id: parent}
    executor = _make_executor(routes, tmp_path)

    result = executor.execute_relation(parent, {})
    assert result.table.column("total").to_pylist() == [3]
    cache_files = list((tmp_path / "cache").rglob("page-*.parquet"))
    assert cache_files, "expected parquet artifacts for dependency"


@pytest.mark.duckdb
def test_route_executor_recovers_after_dependency_failure(tmp_path):
    child_metadata = {
        "cache": {
            "order_by": ["value"],
            "rows_per_page": 5,
            "invariant_filters": [{"param": "value", "column": "value"}],
        }
    }
    child = _make_route(
        "child_with_invariants",
        "SELECT i AS value FROM range(3) AS t(i)",
        metadata=child_metadata,
    )
    failing_parent = _make_route(
        "failing_parent",
        "SELECT COUNT(*) FROM child_view",
        uses=[RouteUse(alias="child_view", call="child_with_invariants", mode="parquet_path")],
    )
    healthy = _make_route("healthy", "SELECT 42 AS answer")
    routes = {child.id: child, failing_parent.id: failing_parent, healthy.id: healthy}
    executor = _make_executor(routes, tmp_path)

    with pytest.raises(RouteExecutionError):
        executor.execute_relation(failing_parent, {})

    recovery = executor.execute_relation(healthy, {})
    assert recovery.table.column("answer").to_pylist() == [42]


@pytest.mark.duckdb
@pytest.mark.skipif(not _HAVE_BENCHMARK, reason="pytest-benchmark plugin not installed")
def test_route_executor_benchmark_fixture(tmp_path, benchmark):
    metadata = {"cache": {"order_by": ["value"], "rows_per_page": 5}}
    route = _make_route(
        "benchmark_route",
        "SELECT value FROM (VALUES (1), (2), (3)) AS t(value)",
        metadata=metadata,
    )
    executor = _make_executor({route.id: route}, tmp_path)

    warmup = executor.execute_relation(route, {})
    assert warmup.used_cache
    assert not warmup.cache_hit

    hits: list[bool] = []

    def run_once() -> int:
        result = executor.execute_relation(route, {})
        hits.append(result.cache_hit)
        return result.table.num_rows

    benchmark(run_once)
    assert hits and all(hits)
