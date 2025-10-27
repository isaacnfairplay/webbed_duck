"""Run routes incrementally with DuckDB-backed checkpoints."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import duckdb

from ..config import Config, load_config
from .local import run_route


@dataclass(slots=True)
class IncrementalResult:
    route_id: str
    cursor_param: str
    value: str
    rows_returned: int


def run_incremental(
    route_id: str,
    *,
    cursor_param: str,
    start: dt.date,
    end: dt.date,
    config: Config | None = None,
    build_dir: str | Path = "routes_build",
    runner: Callable[..., object] = run_route,
) -> list[IncrementalResult]:
    """Run ``route_id`` for each day in ``[start, end]`` inclusive."""

    if config is None:
        config = load_config(None)
    conn = _open_checkpoint_db(config.server.storage_root)
    try:
        last_value = _read_checkpoint(conn, route_id, cursor_param)
        results: list[IncrementalResult] = []
        for current in _date_range(start, end):
            iso_value = current.isoformat()
            if last_value and iso_value <= last_value:
                continue
            table = runner(
                route_id,
                params={cursor_param: iso_value},
                build_dir=build_dir,
                config=config,
                format="arrow",
            )
            rows = _table_row_count(table)
            results.append(
                IncrementalResult(
                    route_id=route_id,
                    cursor_param=cursor_param,
                    value=iso_value,
                    rows_returned=rows,
                )
            )
            _write_checkpoint(conn, route_id, cursor_param, iso_value)
            last_value = iso_value
    finally:
        conn.close()
    return results


def _date_range(start: dt.date, end: dt.date) -> Iterable[dt.date]:
    current = start
    while current <= end:
        yield current
        current += dt.timedelta(days=1)


def _table_row_count(table: object) -> int:
    rows = getattr(table, "num_rows", None)
    if rows is not None:
        return int(rows)
    if hasattr(table, "__len__"):
        return int(len(table))  # type: ignore[arg-type]
    return 0


def _open_checkpoint_db(storage_root: Path) -> duckdb.DuckDBPyConnection:
    runtime = Path(storage_root) / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    path = runtime / "checkpoints.duckdb"
    conn = duckdb.connect(path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS checkpoints (
            route_id TEXT,
            cursor_param TEXT,
            cursor_value TEXT,
            updated_at TIMESTAMP,
            PRIMARY KEY (route_id, cursor_param)
        )
        """
    )
    return conn


def _read_checkpoint(
    conn: duckdb.DuckDBPyConnection, route_id: str, cursor_param: str
) -> str | None:
    row = conn.execute(
        "SELECT cursor_value FROM checkpoints WHERE route_id = ? AND cursor_param = ?",
        (route_id, cursor_param),
    ).fetchone()
    if not row:
        return None
    return row[0]


def _write_checkpoint(
    conn: duckdb.DuckDBPyConnection,
    route_id: str,
    cursor_param: str,
    value: str,
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO checkpoints (route_id, cursor_param, cursor_value, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (route_id, cursor_param, value),
    )


__all__ = ["IncrementalResult", "run_incremental"]
