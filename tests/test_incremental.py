import datetime as dt
from pathlib import Path

import duckdb
import pytest

from tests.conftest import write_sidecar_route
from webbed_duck.core.compiler import compile_routes
from webbed_duck.core.incremental import IncrementalResult, run_incremental
from webbed_duck.config import Config, load_config


ROUTE_TEMPLATE = """
+++
id = "by_date"
path = "/by_date"
[params.day]
type = "str"
required = true
[cache]
order_by = ["day_value"]
+++

```sql
SELECT {{day}} AS day_value
ORDER BY day_value;
```
"""


def _write_route(tmp_path: Path) -> tuple[Path, Path]:
    src_dir = tmp_path / "src"
    build_dir = tmp_path / "build"
    src_dir.mkdir()
    write_sidecar_route(src_dir, "route", ROUTE_TEMPLATE)
    compile_routes(src_dir, build_dir)
    return src_dir, build_dir


def _make_config(storage_root: Path) -> Config:
    config = load_config(None)
    config.server.storage_root = storage_root
    return config


def test_incremental_skips_previous_checkpoint(tmp_path: Path) -> None:
    _, build_dir = _write_route(tmp_path)
    storage_root = tmp_path / "storage"
    config = _make_config(storage_root)

    first_results = run_incremental(
        "by_date",
        cursor_param="day",
        start=dt.date(2025, 1, 1),
        end=dt.date(2025, 1, 3),
        config=config,
        build_dir=build_dir,
    )
    assert [result.value for result in first_results] == [
        "2025-01-01",
        "2025-01-02",
        "2025-01-03",
    ]

    follow_up = run_incremental(
        "by_date",
        cursor_param="day",
        start=dt.date(2024, 12, 31),
        end=dt.date(2025, 1, 4),
        config=config,
        build_dir=build_dir,
    )
    assert [result.value for result in follow_up] == ["2025-01-04"]

    checkpoint_path = storage_root / "runtime" / "checkpoints.duckdb"
    conn = duckdb.connect(checkpoint_path)
    try:
        row = conn.execute(
            "SELECT cursor_value FROM checkpoints WHERE route_id = ? AND cursor_param = ?",
            ("by_date", "day"),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None and row[0] == "2025-01-04"


class _DummyTable:
    def __init__(self, rows: int) -> None:
        self.num_rows = rows


def test_incremental_error_does_not_advance_checkpoint(tmp_path: Path) -> None:
    storage_root = tmp_path / "storage"
    config = _make_config(storage_root)

    calls: list[str] = []

    def failing_runner(route_id, *, params, **kwargs):  # type: ignore[no-untyped-def]
        value = params["day"]
        calls.append(value)
        if value == "2025-01-01":
            raise ValueError("boom")
        return _DummyTable(1)

    with pytest.raises(ValueError):
        run_incremental(
            "by_date",
            cursor_param="day",
            start=dt.date(2025, 1, 1),
            end=dt.date(2025, 1, 2),
            config=config,
            build_dir=tmp_path / "build",
            runner=failing_runner,
        )

    assert calls == ["2025-01-01"]

    checkpoint_path = storage_root / "runtime" / "checkpoints.duckdb"
    conn = duckdb.connect(checkpoint_path)
    try:
        row = conn.execute(
            "SELECT cursor_value FROM checkpoints WHERE route_id = ? AND cursor_param = ?",
            ("by_date", "day"),
        ).fetchone()
    finally:
        conn.close()
    assert row is None

    # A second run with a working runner should process the first day.

    def good_runner(*args, **kwargs) -> _DummyTable:  # type: ignore[no-redef]
        return _DummyTable(2)

    recovery = run_incremental(
        "by_date",
        cursor_param="day",
        start=dt.date(2025, 1, 1),
        end=dt.date(2025, 1, 1),
        config=config,
        build_dir=tmp_path / "build",
        runner=good_runner,
    )
    assert recovery == [
        IncrementalResult(
            route_id="by_date",
            cursor_param="day",
            value="2025-01-01",
            rows_returned=2,
        )
    ]
