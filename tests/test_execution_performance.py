from __future__ import annotations

import time
from pathlib import Path

import duckdb
import pyarrow.parquet as pq

from webbed_duck.config import Config
from webbed_duck.core.compiler import compile_routes
from webbed_duck.core.routes import RouteDefinition, load_compiled_routes
from webbed_duck.server.cache import CacheStore
from webbed_duck.server.execution import RouteExecutor


def _write_taxi_dataset(path: Path, rows: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    try:
        table = con.execute(
            f"""
            SELECT
                (i % 2) + 1 AS vendor_id,
                TIMESTAMP '2024-01-01 00:00:00' + i * INTERVAL 1 MINUTE AS tpep_pickup_datetime,
                TIMESTAMP '2024-01-01 00:15:00' + i * INTERVAL 1 MINUTE AS tpep_dropoff_datetime,
                (i % 4) + 1 AS passenger_count,
                0.5 + (i % 200) * 0.05 AS trip_distance,
                2.5 + (i % 120) * 0.1 AS fare_amount,
                0.5 + (i % 60) * 0.05 AS tip_amount,
                CASE WHEN i % 2 = 0 THEN 'Y' ELSE 'N' END AS store_and_fwd_flag
            FROM range({rows}) AS t(i)
            """
        ).fetch_arrow_table()
    finally:
        con.close()
    pq.write_table(table, path)


def _compile_nyc_route(base: Path, dataset: Path, route_id: str) -> RouteDefinition:
    src = base / "src"
    build = base / "build"
    src.mkdir(parents=True, exist_ok=True)
    build.mkdir(parents=True, exist_ok=True)

    toml_path = src / f"{route_id}.toml"
    sql_path = src / f"{route_id}.sql"

    toml_path.write_text(
        f"""
id = \"{route_id}\"
path = \"/{route_id}\"
title = \"NYC taxi load test {route_id}\"
cache_mode = \"materialize\"
returns = \"relation\"

[cache]
order_by = [\"passenger_count\"]
rows_per_page = 2048
""",
        encoding="utf-8",
    )

    sql_path.write_text(
        f"""
SELECT
    passenger_count,
    COUNT(*) AS trip_count,
    AVG(trip_distance) AS avg_trip_distance,
    AVG(fare_amount + tip_amount) AS avg_total_amount
FROM read_parquet('{dataset.as_posix()}')
GROUP BY passenger_count
ORDER BY passenger_count
""",
        encoding="utf-8",
    )

    compile_routes(src, build)
    routes = load_compiled_routes(build)
    assert len(routes) == 1
    return routes[0]


def _make_executor(route: RouteDefinition, storage_root: Path) -> RouteExecutor:
    config = Config()
    config.server.storage_root = storage_root
    storage_root.mkdir(parents=True, exist_ok=True)
    store = CacheStore(storage_root)
    return RouteExecutor({route.id: route}, cache_store=store, config=config)


def test_nyc_taxi_route_scales_with_load(tmp_path: Path) -> None:
    row_counts = [5_000, 25_000, 75_000]
    page_counts: list[int] = []
    bytes_written: list[int] = []

    for rows in row_counts:
        case_dir = tmp_path / f"nyc_{rows}"
        dataset = case_dir / "data" / "nyc_taxi.parquet"
        _write_taxi_dataset(dataset, rows)
        route = _compile_nyc_route(case_dir, dataset, f"nyc_taxi_{rows}")
        executor = _make_executor(route, case_dir / "storage")

        result = executor.execute_relation(route, params={})

        assert result.table.num_rows == 4
        assert result.total_rows == 4
        assert result.used_cache
        assert not result.cache_hit

        cache_root = case_dir / "storage" / "cache"
        pages = list(cache_root.rglob("page-*.parquet"))
        page_counts.append(len(pages))
        bytes_written.append(sum(int(page.stat().st_size) for page in pages))

    assert all(later >= earlier for earlier, later in zip(page_counts, page_counts[1:]))
    assert max(bytes_written) > min(bytes_written)


def test_nyc_taxi_cache_hits_are_faster(tmp_path: Path) -> None:
    dataset = tmp_path / "data" / "nyc_taxi.parquet"
    _write_taxi_dataset(dataset, 50_000)
    route = _compile_nyc_route(tmp_path, dataset, "nyc_taxi_cache")
    storage = tmp_path / "storage"
    executor = _make_executor(route, storage)

    first_start = time.perf_counter()
    first = executor.execute_relation(route, params={})
    first_elapsed = time.perf_counter() - first_start

    second_start = time.perf_counter()
    second = executor.execute_relation(route, params={})
    second_elapsed = time.perf_counter() - second_start

    assert first.used_cache
    assert not first.cache_hit
    assert second.used_cache
    assert second.cache_hit
    assert second_elapsed <= first_elapsed

    cache_root = storage / "cache"
    parquet_pages = sorted(cache_root.rglob("page-*.parquet"))
    assert parquet_pages, "expected parquet artifacts to exist after cache population"
